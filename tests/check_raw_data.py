import csv
from pathlib import Path

CSV_FILE = Path(__file__).parent.parent / "CrocoDash" /"raw_data_access"/"tables"/ "data_product_registry.csv"

def main():
 with open(CSV_FILE, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            dataset_name = row["Product_Name"]
            print(dataset_name)
if __name__ == "__main__":
    main()