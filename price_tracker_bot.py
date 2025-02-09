import logging
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pytz  # Required for timezone support
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler

# ---------------------- Setup Logging ---------------------- #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------- Database Functions ---------------------- #
DB_FILE = 'price_tracker.db'

def get_db_connection():
    """Return a new SQLite database connection."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def init_db():
    """Initialize the database table if it doesn't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        product_url TEXT,
                        product_name TEXT,
                        last_price REAL,
                        last_checked TIMESTAMP
                      )''')
    conn.commit()
    conn.close()

# ---------------------- Telegram Bot Handlers ---------------------- #
def start(update: Update, context: CallbackContext):
    """Send a welcome message including your name."""
    update.message.reply_text(
        "👋 Welcome! I am the Price Tracker Bot developed by Vyankatesh.\n"
        "Send me an Amazon product link, and I’ll track its price for you."
    )

def help_command(update: Update, context: CallbackContext):
    """Send a help message with instructions."""
    update.message.reply_text(
        "ℹ️ To use this bot:\n"
        "1. Send an Amazon product link to track its price.\n"
        "2. Use /about to learn more about this bot.\n"
        "I’ll alert you when the price drops!"
    )

def about(update: Update, context: CallbackContext):
    """Send a description of the bot including your name."""
    update.message.reply_text(
        "Price Tracker Bot\n"
        "Developed by Vyankatesh.\n"
        "This bot tracks the prices of Amazon products and notifies you when the price drops.\n"
        "Simply send an Amazon product link to get started!"
    )

def handle_link(update: Update, context: CallbackContext):
    """Handle the incoming message that contains an Amazon product link."""
    user_id = update.message.from_user.id
    product_url = update.message.text.strip()

    product_name = get_product_name(product_url)
    if product_name:
        current_price = check_price(product_url)
        if current_price is not None:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO products 
                                  (user_id, product_url, product_name, last_price, last_checked)
                                  VALUES (?, ?, ?, ?, ?)''',
                               (user_id, product_url, product_name, current_price, datetime.now()))
                conn.commit()
                conn.close()
                update.message.reply_text(
                    f'✅ Added "{product_name}" to your tracking list at price ₹{current_price}!'
                )
            except Exception as e:
                logger.error("Error inserting product into database: %s", e)
                update.message.reply_text("❌ There was an error adding your product. Please try again.")
        else:
            update.message.reply_text("❌ Failed to fetch the product price. Please try again later.")
    else:
        update.message.reply_text("❌ Failed to parse the product. Check the link and try again.")

# ---------------------- Web Scraping Functions ---------------------- #
def get_product_name(url):
    """Fetch and return the product name from the given Amazon URL."""
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/91.0.4472.124 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br"
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("span", {"id": "productTitle"})
        if title_tag:
            return title_tag.get_text().strip()
        else:
            logger.error("Product title not found on the page.")
            return None
    except Exception as e:
        logger.error("Error fetching product name: %s", e)
        return None

def check_price(url):
    """Fetch and return the current price from the given Amazon URL."""
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/91.0.4472.124 Safari/537.36"),
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br"
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        price_tag = soup.find("span", {"class": "a-offscreen"})
        if price_tag:
            price_text = price_tag.get_text().strip()
            # Remove the currency symbol and commas (e.g., '₹1,299.00')
            price_text = price_text.replace("₹", "").replace(",", "")
            return float(price_text)
        else:
            logger.error("Price tag not found on the page.")
            return None
    except Exception as e:
        logger.error("Error fetching price: %s", e)
        return None

# ---------------------- Scheduler Function ---------------------- #
def check_all_prices(context: CallbackContext):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, product_url, product_name, last_price FROM products")
        products = cursor.fetchall()
        for product in products:
            prod_id, user_id, url, name, last_price = product
            current_price = check_price(url)
            if current_price is not None and current_price < last_price:
                message = (
                    f'🚨 Price dropped for "{name}"!\n'
                    f'Old Price: ₹{last_price}\n'
                    f'New Price: ₹{current_price}\n'
                    f'{url}'
                )
                context.bot.send_message(chat_id=user_id, text=message)
                cursor.execute(
                    "UPDATE products SET last_price = ?, last_checked = ? WHERE id = ?",
                    (current_price, datetime.now(), prod_id)
                )
                conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Error in check_all_prices: %s", e)

# ---------------------- Main Function ---------------------- #
def main():
    # Initialize the database
    init_db()

    # Use your bot token directly (be cautious with token exposure)
    bot_token = "7606305913:AAGY3JO0jKjOrZyR6y9tK-YR_TYei3gWOcA"
    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher

    # Add command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("about", about))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_link))

    # Set up the scheduler to run the price check every hour.
    # Here we explicitly provide a pytz timezone (UTC in this example).
    scheduler = BackgroundScheduler(timezone=pytz.utc)
    scheduler.add_job(check_all_prices, 'interval', hours=1, args=[updater.bot])
    scheduler.start()

    # Start polling for Telegram updates
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
