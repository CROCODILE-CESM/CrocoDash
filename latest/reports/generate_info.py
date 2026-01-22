"""RERUN THIS WHEN TABLES NEED TO BE UPDATED"""

from CrocoDash.raw_data_access.datasets import load_all_datasets
from CrocoDash.raw_data_access.registry import ProductRegistry
from pathlib import Path
import csv
def main():
    product_info_dict = generate_dict()
    script_dir = Path(__file__).parent
    # --- Write Products CSV ---
    products_csv = Path(script_dir/"products.csv")
    with open(products_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Product", "Description", "Link"])
        for key, value in product_info_dict.items():
            writer.writerow([value["product_name"], value["product_description"], value["link"]])

    # --- Write Functions CSV ---
    functions_csv = Path(script_dir/"functions.csv")
    with open(functions_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Product", "Function", "Type", "Description"])
        for key, value in product_info_dict.items():
            for key2, value2 in value["functions"].items():
                writer.writerow([value["product_name"], key2,value2["type"],value2["description"]])

    print(f"Wrote {products_csv} and {functions_csv}")


def generate_dict():
    load_all_datasets()
    product_info_dict = {}
    for product_key in ProductRegistry.products:
        product_info_dict[product_key] = {
            "product_name": product_key,
            "product_description":  ProductRegistry.products[product_key].description,
            "link": ProductRegistry.products[product_key].link,
            "functions": {}
        }
        for method in ProductRegistry.products[product_key]._access_methods:
            product_info_dict[product_key]["functions"][method] = {
                "description":ProductRegistry.products[product_key]._access_methods[method]._description,
                "type":ProductRegistry.products[product_key]._access_methods[method]._type
            }
    return product_info_dict


if __name__ == "__main__":
    main()