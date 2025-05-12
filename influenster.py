import logging
import csv
import time
import random
import os
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError

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

def scrape_reviews(url=None):
    current_date = datetime(2025, 4, 27)  # Current date as per context
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        all_reviews = []
        seen_reviews = set()  
        
        try:
            # Navigate to the product reviews page
            target_url = url if url else "https://www.influenster.com/reviews/dove-body-lotion-for-sensitive-skin/reviews"
            logging.info(f"Navigating to reviews page: {target_url}")
            page.goto(target_url, timeout=60000)
            time.sleep(5)  # Delay for page load

            # Check if we're on the correct page
            if "profile" in page.url:
                logging.error("Landed on a profile page instead of reviews page. Reviews may only be available in the app.")
                return all_reviews
            
            # Accept cookies
            try:
                page.click("button:has-text('Accept'), button[class*='cookie'], button[id*='accept']", timeout=5000)
                logging.info("Accepted cookies")
                time.sleep(1)
            except:
                logging.info("No cookie button found")

            # Check for CAPTCHA or Cloudflare challenge
            captcha = page.query_selector("iframe[src*='captcha'], div[id*='captcha'], div[class*='recaptcha'], iframe[src*='/cdn-cgi/challenge-platform']")
            if captcha:
                logging.warning("CAPTCHA or Cloudflare challenge detected. Solve it manually in the browser.")
                time.sleep(30)  # Wait for manual CAPTCHA solving

            # Wait for initial reviews to load
            logging.info("Waiting for reviews to load...")
            try:
                page.wait_for_selector("div[class*='UgcContainer_ugc-container__']", timeout=30000)
                logging.info("Review elements found")
            except TimeoutError:
                logging.warning("No review elements found after waiting")
                with open('page_content.html', 'w', encoding='utf-8') as f:
                    f.write(page.content())
                logging.info("Saved page HTML to 'page_content.html' for debugging")
                return all_reviews

            while True:
                # Scroll to ensure all visible reviews are loaded
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(3)

                # Extract current visible reviews
                review_blocks = page.query_selector_all("div[class*='UgcContainer_ugc-container__']")
                new_reviews = []
                
                for idx, review in enumerate(review_blocks):
                    try:
                        # Get unique content hash to avoid duplicates
                        content = review.inner_text()
                        content_hash = hash(content[:200])
                        
                        if content_hash in seen_reviews:
                            continue
                            
                        seen_reviews.add(content_hash)
                        
                        # Scroll into view
                        review.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        
                        # Extract username
                        username = "Unknown"
                        username_elem = review.query_selector("h5[class*='MiniProfileTimestamp_mini-profile-timestamp__profile-name__']")
                        if username_elem:
                            username = username_elem.inner_text().strip()
                        if username == "Unknown":
                            logging.warning(f"Username not found for review {idx}. Full HTML: {review.inner_html()}")

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
                                    logging.info(f"Extracted exact date for review {idx}: {date}")
                                except ValueError:
                                    logging.warning(f"Failed to parse datetime attribute for review {idx}: {datetime_attr}")
                                    date_text = date_elem.inner_text().strip() or "Unknown"
                                    date = parse_relative_date(date_text, current_date)
                            else:
                                date_text = date_elem.inner_text().strip() or "Unknown"
                                date = parse_relative_date(date_text, current_date)
                                logging.info(f"No datetime attribute for review {idx}, calculated date: {date}")
                        else:
                            logging.warning(f"No <time> element found for review {idx}. Full HTML: {review.inner_html()}")
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
                            logging.warning(f"Rating not found for review {idx}. Full HTML: {review.inner_html()}")

                        new_reviews.append({
                            'username': username,
                            'rating': rating,
                            'date': date,
                            'review_text': text,
                            'pros': "",
                            'cons': ""
                        })
                        
                    except Exception as e:
                        logging.warning(f"Skipping review {idx} due to error: {e}")
                        continue
                
                if new_reviews:
                    all_reviews.extend(new_reviews)
                    logging.info(f"Added {len(new_reviews)} reviews (Total: {len(all_reviews)})")
                
                # Try to load more
                try:
                    load_more = page.query_selector("button[class*='InfiniteScroll_infinite-scroll__load-more-button__']")
                    if load_more:
                        load_more.scroll_into_view_if_needed()
                        load_more.click()
                        logging.info("Clicked 'Load More'")
                        time.sleep(random.uniform(3, 5))
                        page.wait_for_selector("div[class*='UgcContainer_ugc-container__']", timeout=5000)
                    else:
                        logging.info("No more 'Load More' button found")
                        break
                except TimeoutError:
                    logging.info("No more 'Load More' button available or new reviews loaded")
                    break
                except Exception as e:
                    logging.warning(f"Error loading more: {e}")
                    break
            
            return all_reviews
            
        except Exception as e:
            logging.error(f"Error during scraping: {e}")
            return all_reviews
            
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
            save_to_csv(reviews)
        else:
            logging.warning("Failed to scrape any reviews. Possible solutions:")
            logging.warning("1. Check browser window for CAPTCHAs or blocks")
            logging.warning("2. Right-click a review and 'Inspect' to share HTML structure")
            logging.warning("3. Check 'page_content.html' for the saved page HTML")
    except Exception as e:
        logging.error(f"Critical error in main execution: {e}")