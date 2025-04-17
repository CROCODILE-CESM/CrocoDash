from CrocoDash.raw_data_access import tables
from CrocoDash.raw_data_access import driver
from datetime import datetime
import pandas as pd
import requests
from pathlib import Path
def main():
    pfd_obj = driver.ProductFunctionRegistry()
    pfd_obj.load_functions()

    results = pd.DataFrame({"Product": [], "Access": [], "Result": []})
    product_df, functions_df = tables.load_tables()

    for product in tables.list_products():
        link = (
            product_df["Links"][product_df["Product_Name"] == product].values[0].strip()
        )
        product_result = check_link(link)

        row = {
            "Product": product,
            "Access": link,
            "Result": bool(product_result)}  # Ensure it's a boolean
        results = pd.concat([results, pd.DataFrame([row])], ignore_index=True)
        
        for func in tables.list_functions(product):
            func_result = pfd_obj.validate_function(product, func)
            row = {
                "Product": product,
                "Access": func,
                "Result": bool(func_result)}  # Ensure it's a boolean
            results = pd.concat([results, pd.DataFrame([row])], ignore_index=True)

    # Ensure 'Result' column is of type bool
    results["Result"] = results["Result"].astype(bool)
    results["Checked At (UTC)"] = datetime.utcnow().isoformat()
    print(results)
    main_dir = Path(__file__).parent.parent  # Get the directory of the current script
    # Save Markdown and HTML
    results.to_html(main_dir/"docs/source/_static/link_check_report.html", index=False)

def check_link(url, timeout=10):
    """Check if a single URL is reachable, avoiding full downloads."""
    url = url.strip()
    if not url:
        return False

    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        if response.status_code == 200:
            return True
    except requests.RequestException:
        pass  # Try GET next

    try:
        response = requests.get(url, stream=True, allow_redirects=True, timeout=timeout)
        next(response.iter_content(chunk_size=1), None)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.RequestException:
        return False


if __name__ == "__main__":
    main()
