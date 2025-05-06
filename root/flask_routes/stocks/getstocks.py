from flask import Blueprint, jsonify, request
import mysql.connector
from flask_cors import cross_origin
import os
from dotenv import load_dotenv
load_dotenv()

app_file103 = Blueprint('app_file103', __name__)

@app_file103.route("/getstocksbygroup", methods=["POST"])
@cross_origin()
def get_stocks_by_group():
    try:
        mydb = mysql.connector.connect(
            host=os.getenv('host'),
            user=os.getenv('user'),
            password=os.getenv('password')
        )
        cursor = mydb.cursor(buffered=True)
        database_sql = "USE {};".format(os.getenv('database'))
        cursor.execute(database_sql)

        data = request.get_json()

        if "outlet_name" not in data or data["outlet_name"] == "":
            return jsonify({"error": "please provide the outlet_name"}), 400
        outlet_name = data["outlet_name"]

        # Step 1: Check if the outlet exists
        outlet_check_sql = "SELECT 1 FROM outetNames WHERE Outlet = %s LIMIT 1"
        cursor.execute(outlet_check_sql, (outlet_name,))
        if cursor.fetchone() is None:
            return jsonify({"error": "Invalid outlet_name. No such outlet exists."}), 404

        # # SQL Query to get stocks grouped by GroupName
        # sql_query = """
        # SELECT `GroupName`, `ItemName`, `BrandName`, `UOM`, `CurrentLevel`, `Rate`, `Total`
        # FROM stock_statement
        # ORDER BY `GroupName`
        # """
        
        # SQL Query to get stocks grouped by GroupName
        sql_query = """
        SELECT `GroupName`, `ItemName`, `BrandName`, `UOM`, `CurrentLevel`, `Rate`, `Total`
        FROM stock_statement WHERE `OutletName`=%s
        ORDER BY `GroupName`
        """

        cursor.execute(sql_query, (outlet_name,))

        # cursor.execute(sql_query)
        result = cursor.fetchall()

        if not result:
            return jsonify({"error": "No stock records found."}), 404

        # Group the results by GroupName
        grouped_stocks = {}
        for row in result:
            group_name = row[0]
            stock = {
                "ItemName": row[1],
                "BrandName": row[2],
                "UOM": row[3],
                "CurrentLevel": row[4],
                "Rate": row[5],
                "Total": row[6]
            }

            if group_name not in grouped_stocks:
                grouped_stocks[group_name] = {
                    "stocks": [],
                    "group_total": 0.0
                }

            # Add stock to the group
            grouped_stocks[group_name]["stocks"].append(stock)

            # Increment the group total
            grouped_stocks[group_name]["group_total"] += stock["Total"]

        # Transform the grouped data into the desired format
        formatted_data = [
            {
                "group": group_name,
                "stocks": group_data["stocks"],
                "group_total": group_data["group_total"]
            }
            for group_name, group_data in grouped_stocks.items()
        ]

        return jsonify(formatted_data), 200

    except mysql.connector.Error as db_error:
        return jsonify({"error": f"Database error: {str(db_error)}"}), 500
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if mydb:
            mydb.close()
