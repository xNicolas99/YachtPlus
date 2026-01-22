from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()

    # Wait for frontend to start (port 8080 as per logs)
    try:
        page.goto("http://localhost:8080", timeout=60000)
    except Exception as e:
        print(f"Goto failed: {e}")
        return

    # Wait for page to load
    page.wait_for_timeout(3000)

    # Take screenshot of Setup or Dashboard
    page.screenshot(path="frontend_verification.png")

    if "setup" in page.url.lower():
        print("At Setup page. This confirms frontend is loading.")
    else:
        print(f"At {page.url}. Frontend loading.")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
