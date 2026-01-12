from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        print("Navigating to http://localhost:8080/")
        page.goto("http://localhost:8080/")

        # Wait a bit for redirects (e.g. to /login)
        page.wait_for_timeout(3000)

        print(f"Current URL: {page.url}")
        print(f"Page Title: {page.title()}")

        # Take screenshot
        page.screenshot(path="frontend_verification.png")
        print("Screenshot saved to frontend_verification.png")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
