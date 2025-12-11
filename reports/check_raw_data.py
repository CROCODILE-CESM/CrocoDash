from datetime import datetime
import pandas as pd
import requests
from pathlib import Path
from generate_info import generate_dict
from CrocoDash.raw_data_access.registry import ProductRegistry


def main():
    print("🔍 Generating product dictionary...")
    product_info_dict = generate_dict()
    print(f"   → Found {len(product_info_dict)} products\n")

    rows = []

    for key, value in product_info_dict.items():
        print(f"=== Checking product: {key} ===")

        # ---- Check link ----
        link = value["link"]
        print(f"  • Checking primary link: {link}")
        product_result = check_link(link)
        print(f"    → Link status: {'OK' if product_result else 'FAIL'}")

        rows.append(
            {
                "Product": key,
                "Access": link,
                "Result": bool(product_result),
            }
        )

        # ---- Check registry functions ----
        for func in value["functions"]:
            print(f"  • Validating access function: {func}")
            func_result = ProductRegistry.validate_function(key, func)
            print(f"    → Function status: {'OK' if func_result else 'FAIL'}")

            rows.append(
                {
                    "Product": key,
                    "Access": func,
                    "Result": bool(func_result),
                }
            )

        print()  # spacing

    # Build DataFrame once
    results = pd.DataFrame(rows)
    results["Checked At (UTC)"] = datetime.utcnow().isoformat()

    print("\n📊 Final results:")
    print(results)

    # Save HTML
    script_dir = Path(__file__).parent
    out_html = script_dir / "raw_data_status.html"
    results.to_html(out_html, index=False)
    print(f"\n💾 Saved HTML report to: {out_html}")


def check_link(url, timeout=10):
    """Check if a single URL is reachable, avoiding full downloads."""
    url = url.strip()
    if not url:
        print("    ⚠️ Empty URL, skipping")
        return False

    # Try HEAD first
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
    except requests.RequestException as e:
        print(f"    ⚠️ HEAD request failed: {e}")

    # Fall back to GET
    try:
        response = requests.get(url, stream=True, allow_redirects=True, timeout=timeout)
        next(response.iter_content(chunk_size=1), None)
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"    ⚠️ GET request failed: {e}")
        return False


if __name__ == "__main__":
    main()
