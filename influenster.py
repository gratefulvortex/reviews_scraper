import logging
import csv
import time
import random
import os
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

os.makedirs('csvlist', exist_ok=True)

def generate_filename():
    """Generate a timestamped filename for the CSV."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join('csvlist', f'influenster_reviews_{timestamp}.csv')

def parse_relative_date(relative_date, current_date):
    """Convert relative date (e.g., '2 days ago', '2d ago') to actual date."""
    try:
        relative_date = relative_date.lower().strip()
        
        # Handle various formats of relative dates
        patterns = [
            (r'(\d+)\s*(?:day|days|d)\s*(?:ago)?', 'days'),  # e.g., "2 days ago", "2d ago"
            (r'(\d+)\s*(?:hour|hours|hr|hrs|h)\s*(?:ago)?', 'hours'),  # e.g., "3 hours ago", "3h ago"
            (r'(\d+)\s*(?:month|months|mo|mos|m)\s*(?:ago)?', 'months'),  # e.g., "1 month ago", "1mo ago"
            (r'(\d+)\s*(?:year|years|yr|yrs|y)\s*(?:ago)?', 'years')  # e.g., "1 year ago", "1y ago"
        ]
        
        for pattern, unit in patterns:
            match = re.match(pattern, relative_date)
            if match:
                value = int(match.group(1))
                if unit == "days":
                    delta = timedelta(days=value)
                elif unit == "hours":
                    delta = timedelta(hours=value)
                elif unit == "months":
                    delta = timedelta(days=value * 30)  # Approximate
                elif unit == "years":
                    delta = timedelta(days=value * 365)  # Approximate
                return (current_date - delta).strftime('%Y-%m-%d')
        
        # If no pattern matches, return the original string
        return relative_date
    except Exception as e:
        logging.warning(f"Failed to parse relative date '{relative_date}': {e}")
        return relative_date

def extract_review_data(review, current_date):
    """Extract data from a single review element."""
    try:
        content = review.inner_text()
        content_hash = hash(content[:200])
        
        # Extract username
        username = "Unknown"
        username_elem = review.query_selector("h5[class*='MiniProfileTimestamp_mini-profile-timestamp__profile-name__']")
        if username_elem:
            username = username_elem.inner_text().strip()

        # Extract date
        date = "Unknown"
        date_elem = review.query_selector("time")
        if date_elem:
            # Try to get the datetime attribute for exact date
            datetime_attr = date_elem.get_attribute("datetime")
            if datetime_attr:
                try:
                    parsed_date = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                    date = parsed_date.strftime('%Y-%m-%d')
                    logging.info(f"Extracted exact date for review: {date}")
                except ValueError:
                    logging.warning(f"Failed to parse datetime attribute for review: {datetime_attr}")
                    date_text = date_elem.inner_text().strip() or "Unknown"
                    date = parse_relative_date(date_text, current_date)
            else:
                date_text = date_elem.inner_text().strip() or "Unknown"
                date = parse_relative_date(date_text, current_date)
                logging.info(f"No datetime attribute for review, calculated date: {date}")
        else:
            logging.warning(f"No <time> element found for review. Full HTML: {review.inner_html()}")
            date = "Date not found"

        # Extract review text
        text_elem = review.query_selector("div[class*='Review_review__body-text__']")
        text = text_elem.inner_text().strip() if text_elem else ""

        # Extract rating
        rating = 0
        rating_container = review.query_selector("div[class*='StarRating_star-rating__']")
        if rating_container:
            rating_elem = rating_container.query_selector("div[class*='StarRating_star-rating__rating-text__']")
            if rating_elem:
                rating_text = rating_elem.inner_text().strip()
                rating_match = re.search(r'(\d+)\s*/\s*5', rating_text)
                if rating_match:
                    rating = int(rating_match.group(1))
        if rating == 0:
            logging.warning(f"Rating not found for review. Full HTML: {review.inner_html()}")

        return {
            'content_hash': content_hash,
            'username': username,
            'rating': rating,
            'date': date,
            'review_text': text,
            'pros': "",
            'cons': ""
        }
    except Exception as e:
        logging.warning(f"Error extracting review data: {e}")
        return None

def process_review_batch(page, review_blocks, current_date, seen_reviews):
    """Process a batch of reviews in parallel."""
    reviews = []
    for review in review_blocks:
        try:
            review.scroll_into_view_if_needed()
            time.sleep(0.1)  # Reduced wait time
            review_data = extract_review_data(review, current_date)
            if review_data and review_data['content_hash'] not in seen_reviews:
                seen_reviews.add(review_data['content_hash'])
                reviews.append(review_data)
        except Exception as e:
            logging.warning(f"Error processing review: {e}")
            continue
    return reviews

def scrape_reviews(url=None):
    current_date = datetime(2025, 4, 27)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # Run in headless mode for speed
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        all_reviews = []
        seen_reviews = set()
        load_more_attempts = 0
        max_load_more_attempts = 200
        no_new_reviews_count = 0
        max_no_new_reviews = 5
        product_image = None
        
        try:
            # Navigate to the product reviews page
            target_url = url if url else "https://www.influenster.com/reviews/dove-body-lotion-for-sensitive-skin/reviews"
            logging.info(f"Navigating to reviews page: {target_url}")
            page.goto(target_url, timeout=60000)
            time.sleep(2)  # Reduced initial wait time

            # Get product image
            try:
                image_selectors = [
                    "img[class*='product-image']",
                    "img[class*='ProductImage']",
                    "img[class*='product-img']",
                    "img[class*='product-picture']",
                    "img[alt*='product']",
                    "img[alt*='Product']"
                ]
                
                for selector in image_selectors:
                    img_element = page.query_selector(selector)
                    if img_element:
                        product_image = img_element.get_attribute('src')
                        if product_image:
                            logging.info(f"Found product image: {product_image}")
                            break
            except Exception as e:
                logging.warning(f"Failed to get product image: {e}")

            # Accept cookies if present
            try:
                page.click("button:has-text('Accept'), button[class*='cookie'], button[id*='accept']", timeout=5000)
                time.sleep(0.5)
            except:
                pass

            # Wait for initial reviews
            try:
                page.wait_for_selector("div[class*='UgcContainer_ugc-container__']", timeout=30000)
            except TimeoutError:
                logging.warning("No review elements found after waiting")
                return {
                    'reviews': all_reviews,
                    'product_image': product_image
                }

            # Main scraping loop
            while load_more_attempts < max_load_more_attempts and no_new_reviews_count < max_no_new_reviews:
                # Scroll to load more reviews
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)  # Reduced wait time

                # Get visible reviews
                review_blocks = page.query_selector_all("div[class*='UgcContainer_ugc-container__']")
                
                # Process reviews in parallel
                with ThreadPoolExecutor(max_workers=4) as executor:
                    batch_size = 10
                    for i in range(0, len(review_blocks), batch_size):
                        batch = review_blocks[i:i + batch_size]
                        reviews = process_review_batch(page, batch, current_date, seen_reviews)
                        if reviews:
                            all_reviews.extend(reviews)
                            no_new_reviews_count = 0
                        else:
                            no_new_reviews_count += 1

                # Try to load more
                try:
                    load_more_selectors = [
                        "button:has-text('LOAD MORE')",
                        "button[class*='InfiniteScroll_infinite-scroll__load-more-button__']",
                        "button[class*='load-more-button']",
                        "button[class*='LOAD-MORE']",
                        "button[class*='load-more']",
                        "button:has-text('Load More')",
                        "button:has-text('Load more')"
                    ]
                    
                    load_more = None
                    for selector in load_more_selectors:
                        try:
                            load_more = page.query_selector(selector)
                            if load_more and load_more.is_visible():
                                break
                        except:
                            continue
                    
                    if load_more:
                        load_more.scroll_into_view_if_needed()
                        time.sleep(0.5)  # Reduced wait time
                        
                        if load_more.is_visible() and load_more.is_enabled():
                            page.evaluate("(button) => button.click()", load_more)
                            load_more_attempts += 1
                            time.sleep(1)  # Reduced wait time
                        else:
                            break
                    else:
                        break
                        
                except Exception as e:
                    logging.warning(f"Error loading more: {e}")
                    break

            logging.info(f"Finished scraping. Total reviews collected: {len(all_reviews)}")
            return {
                'reviews': all_reviews,
                'product_image': product_image
            }
            
        except Exception as e:
            logging.error(f"Error during scraping: {e}")
            return {
                'reviews': all_reviews,
                'product_image': product_image
            }
            
        finally:
            browser.close()

def save_to_csv(reviews):
    if not reviews:
        logging.warning("No reviews to save")
        return
    
    # Generate timestamped filename
    filename = generate_filename()
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['username', 'rating', 'date', 'review_text', 'pros', 'cons'])
            writer.writeheader()
            writer.writerows(reviews)
        logging.info(f"Saved {len(reviews)} reviews to {filename}")
    except Exception as e:
        logging.error(f"Failed to save reviews to {filename}: {e}")
        raise

if __name__ == "__main__":
    logging.info("Starting review scraping...")
    try:
        reviews = scrape_reviews()
        if reviews:
            save_to_csv(reviews['reviews'])
        else:
            logging.warning("Failed to scrape any reviews. Possible solutions:")
            logging.warning("1. Check browser window for CAPTCHAs or blocks")
            logging.warning("2. Right-click a review and 'Inspect' to share HTML structure")
            logging.warning("3. Check 'page_content.html' for the saved page HTML")
    except Exception as e:
        logging.error(f"Critical error in main execution: {e}")