from flask import Blueprint, request, jsonify
import mysql.connector
from flask_cors import cross_origin
import os
from dotenv import load_dotenv
from datetime import datetime
import pytz

from .cost_utils import calculate_food_and_beverage_stockstatement, calculate_food_and_beverage_purchase, insert_into_tblcosttracker,calculate_food_and_beverage_from_newposted_stockstatement
import copy


from datetime import datetime
load_dotenv()

app_file104 = Blueprint('app_file104', __name__)

@app_file104.route("/poststocks", methods=["POST"])
@cross_origin()
def stats():
    try:
        mydb = mysql.connector.connect(
            host=os.getenv('host'),
            user=os.getenv('user'),
            password=os.getenv('password')
        )
        cursor = mydb.cursor(buffered=True)
        database_sql = "USE {};".format(os.getenv('database'))
        cursor.execute(database_sql)
        
        # Get the list of stocks from the request body
        stock_data_json = request.get_json()

        posted_data = copy.deepcopy(stock_data_json)
        stock_data = stock_data_json["ItemDetailsList"]

        if "OutletName" not in stock_data_json or stock_data_json["OutletName"] == "":
            return jsonify({"error": "OutletName is required"}), 400
        outlet_name = stock_data_json["OutletName"]
        print(stock_data)

        if not stock_data or not isinstance(stock_data, list):
            return jsonify({"error": "Invalid input. A list of stocks is required."}), 400
        
        # Data validation
        for stock in stock_data:
            if not isinstance(stock.get('currentLevel'), (int, float)) or stock.get('currentLevel') < 0:
                return jsonify({"error": "Invalid 'Current Level'. Must be a positive number."}), 400
            if not isinstance(stock.get('Rate'), (int, float)):
                return jsonify({"error": "Invalid 'Rate'. Must be a number."}), 400
            if not isinstance(stock.get('Total'), (int, float)):
                return jsonify({"error": "Invalid 'Total'. Must be a number."}), 400
            if stock.get('Department', None) is None:
                return jsonify({"error": "Invalid 'Department'. Must be passed."}), 400
            

        # this function gives us the openigfood_total and beveragetotal in the case of previouly available stock statement for the passes outlet
        opening_foodtotal, opening_beveragetotal = calculate_food_and_beverage_stockstatement(cursor, outlet_name)


        # Delete all existing entries in the stock_statement table
        sql_delete = "DELETE FROM stock_statement WHERE OutletName=%s"
        cursor.execute(sql_delete, (outlet_name,))

        # Insert the new list of stocks into the stock_statement table
        sql_insert = """
        INSERT INTO stock_statement (`GroupName`, `ItemName`, `BrandName`, `UOM`, `CurrentLevel`, `Rate`, `Total`, `OutletName`, `Type`)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) 
        """
        
        # Prepare data for insertion
        stock_entries = [(stock.get('GroupName'), stock.get('ItemName'), stock.get('BrandName'),
                          stock.get('UOM'), stock.get('currentLevel'), stock.get('Rate'), stock.get('Total'), stock.get('OutletName'), stock.get('Department'))
                         for stock in stock_data]

        # Insert the data in batches
        cursor.executemany(sql_insert, stock_entries)

        # Get current time in Nepali time (NST)
        nepal_tz = pytz.timezone('Asia/Kathmandu')
        current_datetime = datetime.now(nepal_tz).strftime('%Y-%m-%d %H:%M:%S')

        # Check if there's already a record in the organization table
        sql_check = "SELECT COUNT(*), DATE(last_synced) FROM organization WHERE outlet_name=%s"
        cursor.execute(sql_check, (outlet_name,))
        result = cursor.fetchone()

        count = result[0]
        last_synced = result[1]

        # If last_synced is not None, format it to a string with just the date part
        if last_synced:
            last_synced_date = last_synced.strftime('%Y-%m-%d')
        else:
            last_synced_date = None

        today_date = datetime.now(nepal_tz).strftime('%Y-%m-%d')

        if last_synced_date is not None:
            # This function calculates the foodtotal and beveragetotal for the purchases from last_synced stock_date to the current date in the purchase table 
            purchase_foodtotal, purchase_beveragetotal = calculate_food_and_beverage_purchase(last_synced_date, today_date, outlet_name, cursor)
        
        
        # This function calculates the foodtotal and beveragetotal for the closing that is from newly posted data 

        closing_foodtotal, closing_beveragetotal = calculate_food_and_beverage_from_newposted_stockstatement(posted_data)
        if last_synced_date is not None:
            if opening_foodtotal != 0.0:
                insert_into_tblcosttracker(today_date, purchase_foodtotal, opening_foodtotal,  closing_foodtotal,  outlet_name, "Food")
        if last_synced_date is not None:
            if opening_beveragetotal != 0.0:
                insert_into_tblcosttracker(today_date,  purchase_beveragetotal,  opening_beveragetotal,  closing_beveragetotal, outlet_name, "Beverage")

        if count == 0:
            # Insert the current datetime if no record exists
            sql_insert_last_synced = "INSERT INTO organization (`last_synced`, `outlet_name`) VALUES (%s, %s)"
            cursor.execute(sql_insert_last_synced, (current_datetime,outlet_name,))
        else:
            # Update the last_synced field if a record exists
            sql_update_last_synced = "UPDATE organization SET `last_synced` = %s WHERE `last_synced` IS NOT NULL AND outlet_name=%s"
            cursor.execute(sql_update_last_synced, (current_datetime,outlet_name,))

        # Commit the changes to the database
        mydb.commit()

        return jsonify({"success": f"Successfully updated stock statement with {len(stock_entries)} records."}), 200

    except mysql.connector.Error as db_error:
        mydb.rollback()  # Rollback on error
        return jsonify({"error": f"Database error: {str(db_error)}"}), 500
    except Exception as e:
        mydb.rollback()  # Rollback on unexpected error
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if mydb:
            mydb.close()