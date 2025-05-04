import logging
import time
import csv
import os
import random
import re
from datetime import datetime
from hashlib import md5
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def generate_csv_filename():
    """Generate a unique CSV filename with timestamp."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'amazon_reviews_{timestamp}.csv'

def get_review_id(review):
    """Generate a unique ID for a review based on its content."""
    content = f"{review.get('title', '')}{review.get('rating', '')}{review.get('date', '')}{review.get('text', '')}"
    return md5(content.encode('utf-8')).hexdigest()

def extract_star_rating(rating_text):
    """Extract numeric star rating (e.g., '4.0 out of 5 stars' -> 4)."""
    if not rating_text or rating_text == "N/A":
        return None
    match = re.search(r'(\d)\.\d\s+out\s+of\s+5\s+stars', rating_text)
    return int(match.group(1)) if match else None

def scrape_amazon_reviews(product_url):
    """Amazon review scraper to extract all reviews using filterByStar URLs."""
    all_reviews = []
    seen_ids = set()
    saved_ids = set()  # Track IDs of reviews already saved to CSV
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0"
    ]
    csv_file = generate_csv_filename()

    # Write CSV header
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['id', 'title', 'rating', 'date', 'text', 'verified', 'helpful'])
        writer.writeheader()

    with sync_playwright() as p:
        # Configure browser
        browser = p.chromium.launch(
            headless=False,
            slow_mo=300,
            args=['--disable-blink-features=AutomationControlled', '--start-maximized']
        )
        context = browser.new_context(
            user_agent=random.choice(user_agents),
            viewport={'width': 1280, 'height': 1024},
            locale='en-US',
            timezone_id='America/New_York',
            storage_state="auth.json" if os.path.exists("auth.json") else None
        )
        page = context.new_page()

        try:
            # Step 1: Navigate to product page
            logger.info(f"Loading product page: {product_url}")
            page.goto(product_url, timeout=60000, wait_until="domcontentloaded")

            # Step 2: Handle login if required
            if any(keyword in page.url for keyword in ["signin", "ap/signin", "login"]):
                logger.info("Please login manually in the browser window")
                page.wait_for_url(
                    lambda url: not any(k in url for k in ["signin", "ap/signin"]),
                    timeout=120000
                )
                logger.info("Success: Login successful, saving session...")
                context.storage_state(path="auth.json")
                page.goto(product_url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(random.uniform(2, 4))

            # Step 3: Check for CAPTCHA
            if "captcha" in page.url.lower() or page.query_selector("form[action*='captcha']"):
                logger.info("CAPTCHA detected, please solve manually in the browser")
                page.wait_for_url(
                    lambda url: "captcha" not in url.lower(),
                    timeout=120000
                )
                logger.info("Success: CAPTCHA solved, resuming scraping")
                page.goto(product_url, timeout=60000, wait_until="domcontentloaded")

            # Step 4: Select "Most recent" sort
            try:
                sort_dropdown = page.query_selector("select#sort-order-dropdown")
                if sort_dropdown:
                    logger.info("Selecting 'Most recent' sort")
                    sort_dropdown.select_option(value="recent")
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    time.sleep(random.uniform(2, 4))
            except:
                logger.info("No sort dropdown found")

            # Step 5: Wait for reviews section
            logger.info("Waiting for reviews to load...")
            review_section = None
            selectors = [
                ("css", "#cm_cr-review_list"),
                ("css", "div[data-hook='reviews-medley-footer']"),
                ("xpath", "//div[contains(@class, 'review')]"),
                ("xpath", "//div[contains(@id, 'customer_review-')]")
            ]
            for selector_type, selector in selectors:
                try:
                    if selector_type == "css":
                        review_section = page.wait_for_selector(selector, state="visible", timeout=10000)
                    elif selector_type == "xpath":
                        review_section = page.wait_for_selector(f"xpath={selector}", state="visible", timeout=10000)
                    if review_section:
                        logger.info(f"Success: Found reviews using {selector_type}: {selector}")
                        break
                except:
                    continue
            if not review_section:
                logger.error("Failed to locate review section")
                page.screenshot(path="review_load_error.png")
                with open("page_content.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                logger.info("Saved page content to page_content.html")
                return []

            # Step 6: Log total reviews
            try:
                total_reviews_elem = page.query_selector("div[data-hook='cr-filter-info-section'] span")
                total_reviews_text = total_reviews_elem.inner_text().strip() if total_reviews_elem else "N/A"
                logger.info(f"Total reviews reported: {total_reviews_text}")
            except:
                logger.info("Could not find total reviews count")

            # Step 7: Scrape reviews for each star rating using filterByStar
            star_filters = [
                ("All", "", None),
                ("5-star", "&filterByStar=five_star", 5),
                ("4-star", "&filterByStar=four_star", 4),
                ("3-star", "&filterByStar=three_star", 3),
                ("2-star", "&filterByStar=two_star", 2),
                ("1-star", "&filterByStar=one_star", 1)
            ]
            for filter_name, star_filter, expected_stars in star_filters:
                page_num = 1
                mismatched_ratings = 0
                max_mismatches = 5
                while True:
                    filter_url = f"{product_url}{star_filter}&pageNumber={page_num}"
                    if star_filter:
                        filter_url = filter_url.replace("ref=cm_cr_dp_d_show_all_btm", "ref=cm_cr_arp_d_viewopt_sr")
                    logger.info(f"Loading reviews for filter: {filter_name} ({filter_url})")
                    page.goto(filter_url, timeout=60000, wait_until="domcontentloaded")
                    time.sleep(random.uniform(2, 4))

                    logger.info(f"Processing page {page_num} for filter {filter_name}")
                    # Scroll to load all content
                    for _ in range(5):
                        page.evaluate("""() => {
                            window.scrollBy(0, document.body.scrollHeight);
                            return new Promise(resolve => setTimeout(resolve, 2000));
                        }""")
                        time.sleep(random.uniform(1, 3))

                    # Find review elements
                    review_elements = []
                    review_selectors = [
                        ("css", "div[data-hook='review'][id^='customer_review-']"),
                        ("css", "div.a-section.review.aok-relative[id^='customer_review-']"),
                        ("xpath", "//div[contains(@id, 'customer_review-')]")
                    ]
                    for selector_type, selector in review_selectors:
                        try:
                            if selector_type == "css":
                                review_elements = page.query_selector_all(selector)
                            elif selector_type == "xpath":
                                review_elements = page.query_selector_all(f"xpath={selector}")
                            if review_elements:
                                logger.info(f"Found {len(review_elements)} reviews using {selector_type}: {selector}")
                                break
                        except:
                            continue
                    if not review_elements:
                        logger.info(f"No reviews found for filter {filter_name} on page {page_num}")
                        page.screenshot(path=f"no_reviews_page_{page_num}_{filter_name}.png")
                        break

                    # Extract review data
                    for review in review_elements:
                        try:
                            # Handle "Read more" links
                            read_more = review.query_selector("a[data-hook='review-see-more-link']")
                            if read_more:
                                read_more.click()
                                page.wait_for_timeout(1000)

                            # Title
                            title_elem = (
                                review.query_selector("span[data-hook='review-title'] > span") or
                                review.query_selector("a[data-hook='review-title'] > span") or
                                review.query_selector("span.review-title") or
                                review.query_selector("div[data-hook='review-title']")
                            )
                            title = title_elem.inner_text().strip() if title_elem else "N/A"

                            # Rating
                            rating_elem = (
                                review.query_selector("i[data-hook='review-star-rating'] > span.a-icon-alt") or
                                review.query_selector("i.a-icon-star > span.a-icon-alt") or
                                review.query_selector("span.a-icon-alt")
                            )
                            rating = "N/A"
                            if rating_elem:
                                rating_text = rating_elem.inner_text().strip()
                                rating = rating_text if rating_text else "N/A"

                            # Validate rating against filter
                            if expected_stars:
                                actual_stars = extract_star_rating(rating)
                                if actual_stars and actual_stars != expected_stars:
                                    logger.warning(f"Mismatched rating: expected {expected_stars}-star, got {actual_stars}-star")
                                    mismatched_ratings += 1
                                    if mismatched_ratings >= max_mismatches:
                                        logger.info(f"Stopping filter {filter_name} due to too many mismatched ratings")
                                        break
                                    continue

                            # Date
                            date_elem = (
                                review.query_selector("span[data-hook='review-date']") or
                                review.query_selector("span.review-date")
                            )
                            date = date_elem.inner_text().strip() if date_elem else "N/A"

                            # Text
                            text_elem = (
                                review.query_selector("span[data-hook='review-body'] > span") or
                                review.query_selector("span.review-text-content") or
                                review.query_selector("div.review-text")
                            )
                            text = text_elem.inner_text().strip() if text_elem else "N/A"

                            # Verified purchase
                            verified_elem = (
                                review.query_selector("span[data-hook='avp-badge']") or
                                review.query_selector("span.a-size-mini.a-color-state")
                            )
                            verified = bool(verified_elem)

                            # Helpful count
                            helpful_elem = (
                                review.query_selector("span[data-hook='helpful-vote-statement']") or
                                review.query_selector("span.a-size-base.a-color-tertiary")
                            )
                            helpful = helpful_elem.inner_text().strip() if helpful_elem else "0 people found this helpful"

                            # Create review data
                            review_data = {
                                'id': get_review_id({'title': title, 'rating': rating, 'date': date, 'text': text}),
                                'title': title,
                                'rating': rating,
                                'date': date,
                                'text': text,
                                'verified': verified,
                                'helpful': helpful
                            }

                            # Check for duplicates
                            if review_data['id'] not in seen_ids:
                                all_reviews.append(review_data)
                                seen_ids.add(review_data['id'])
                                logger.info(f"Collected review: {title[:50]}... (Rating: {rating})")
                            else:
                                logger.info(f"Skipped duplicate review: {title[:50]}...")

                            # Log missing fields
                            missing_fields = [field for field, value in [('title', title), ('rating', rating), ('date', date), ('text', text)] if value == "N/A"]
                            if missing_fields:
                                logger.warning(f"Review with missing fields: {missing_fields}, title={title[:50]}...")

                        except Exception as e:
                            logger.warning(f"Error extracting review: {e}")
                            continue
                    if mismatched_ratings >= max_mismatches:
                        break

                    # Save reviews incrementally
                    if all_reviews:
                        try:
                            new_reviews = [r for r in all_reviews if r['id'] not in saved_ids]
                            if new_reviews:
                                with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                                    writer = csv.DictWriter(f, fieldnames=['id', 'title', 'rating', 'date', 'text', 'verified', 'helpful'])
                                    writer.writerows(new_reviews)
                                saved_ids.update(r['id'] for r in new_reviews)
                                logger.info(f"Incremental save: {len(new_reviews)} new reviews, total {len(all_reviews)} reviews to {csv_file}")
                            else:
                                logger.info(f"No new reviews to save, total {len(all_reviews)} reviews collected")
                        except Exception as e:
                            logger.error(f"Failed to save CSV incrementally: {e}")

                    # Handle pagination
                    try:
                        next_button = None
                        pagination_selectors = [
                            "li.a-last a",
                            "a[data-hook='pagination-bar'] a:has-text('Next page')",
                            "a:has-text('Next page')",
                            "a.a-last",
                            "a.a-pagination__next"
                        ]
                        for selector in pagination_selectors:
                            next_button = page.query_selector(selector)
                            if next_button and next_button.is_enabled() and next_button.is_visible():
                                logger.info(f"Found next page button with selector: {selector}")
                                break
                        if next_button:
                            logger.info("Navigating to next page...")
                            next_button.scroll_into_view_if_needed()
                            next_button.hover()
                            time.sleep(random.uniform(0.5, 1.5))
                            max_retries = 3
                            for attempt in range(max_retries):
                                try:
                                    next_button.click()
                                    page.wait_for_selector("#cm_cr-review_list", timeout=30000)
                                    break
                                except Exception as e:
                                    logger.warning(f"Pagination attempt {attempt + 1} failed: {e}")
                                    if attempt == max_retries - 1:
                                        raise Exception("Max retries reached")
                                    time.sleep(random.uniform(5, 10))
                            page_num += 1
                            time.sleep(random.uniform(3, 5))
                            mismatched_ratings = 0
                        else:
                            logger.info(f"No more pages available for filter {filter_name}")
                            pagination_area = page.query_selector("div[data-hook='pagination-bar']") or page.query_selector("ul.a-pagination")
                            if pagination_area:
                                logger.info(f"Pagination HTML: {pagination_area.inner_html()[:2000]}")
                            break
                    except Exception as e:
                        logger.error(f"Pagination error: {e}")
                        page.screenshot(path=f"pagination_error_page_{page_num}_{filter_name}.png")
                        with open(f"pagination_error_page_{page_num}_{filter_name}.html", "w", encoding="utf-8") as f:
                            f.write(page.content())
                        logger.info(f"Saved pagination error screenshot and HTML for page {page_num}")
                        break

            # Step 8: Final save and stats
            if all_reviews:
                try:
                    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=['id', 'title', 'rating', 'date', 'text', 'verified', 'helpful'])
                        writer.writeheader()
                        writer.writerows(all_reviews)
                    logger.info(f"Success: Saved {len(all_reviews)} reviews to {csv_file}")

                    # Log stats
                    rating_counts = {'5': 0, '4': 0, '3': 0, '2': 0, '1': 0, 'N/A': 0}
                    missing_stats = {'title': 0, 'rating': 0, 'date': 0, 'text': 0}
                    for review in all_reviews:
                        stars = extract_star_rating(review['rating'])
                        rating_counts[str(stars) if stars else 'N/A'] += 1
                        if review['title'] == "N/A":
                            missing_stats['title'] += 1
                        if review['rating'] == "N/A":
                            missing_stats['rating'] += 1
                        if review['date'] == "N/A":
                            missing_stats['date'] += 1
                        if review['text'] == "N/A":
                            missing_stats['text'] += 1
                    logger.info(f"Rating distribution: {rating_counts}")
                    logger.info(f"Missing fields stats: {missing_stats}")
                    return all_reviews
                except Exception as e:
                    logger.error(f"Failed to save CSV: {e}")
                    return all_reviews
            else:
                logger.warning("No reviews were extracted")
                return []

        except Exception as e:
            logger.error(f"Critical error: {e}")
            try:
                page.screenshot(path="critical_error.png", timeout=10000)
            except:
                logger.error("Could not take screenshot")
            return []
        finally:
            try:
                browser.close()
            except:
                pass

if __name__ == "__main__":
    # Example URL (base URL without star filter)
    url = "https://www.amazon.in/product-reviews/B07L1SP25K/ref=cm_cr_dp_d_show_all_btm?ie=UTF8&reviewerType=all_reviews  "
    print("Starting Amazon Review Scraper...")
    print(f"Product URL: {url}")
    reviews = scrape_amazon_reviews(url)
    if reviews:
        print("\nSample Review:")
        print(f"Title: {reviews[0]['title']}")
        print(f"Rating: {reviews[0]['rating']}")
        print(f"Date: {reviews[0]['date']}")
        print(f"Verified: {'Yes' if reviews[0]['verified'] else 'No'}")
        print(f"Helpful: {reviews[0]['helpful']}")
        print(f"Text: {reviews[0]['text'][:100]}...")
        print(f"\nSuccess: Extracted {len(reviews)} reviews")
    else:
        print("\nFailed to extract reviews. Check error logs and screenshots.")