import csv
from pathlib import Path

CSV_FILE = Path(__file__).parent.parent / "CrocoDash" /"raw_data_access"/"tables"/ "data_product_registry.csv"

def main():
    results = {}
    with open(CSV_FILE, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            dataset_name = row["Product_Name"]
            results[dataset_name] = {
                "links":{},
                "module":{}
            }
            links = row["Links"]
            

if __name__ == "__main__":
    main()