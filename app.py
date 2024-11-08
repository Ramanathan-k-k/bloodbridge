from flask import Flask, render_template, flash, url_for, redirect, request, session
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import Error, connect
import json
from datetime import date, timedelta
from config import HOST, USERNAME, PASSWORD, DATABASE, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY  # Needed for Flash msgs

# Database config
db_config = { 'host': HOST, 'user': USERNAME, 'password': PASSWORD, 'database': DATABASE }

cnxpool = MySQLConnectionPool(pool_name="mypool",pool_size=16,**db_config)

def get_db_connection():
    try:
        return cnxpool.get_connection()
    except Error as err:
        print(f"Error: {err}")
        return None

@app.route("/test-db-connection")
def test_db_connection():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE();")
        db_name = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"Connected to the database: {db_name[0]}"
    except Error as err:
        return f"Error: {err}"

# User Data in Session
try:
    with open('users.json', 'r') as f:
        users_data = json.load(f)
except FileNotFoundError:
    users_data = {}

# Function to refresh the users JSON cache from the database
def refresh_user_data():
    conn = connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT email, full_name, blood_type, pincode, role FROM users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    # Index users by email and write to JSON
    users_dict = {user['email']: user for user in users}
    with open('users.json', 'w') as f:
        json.dump(users_dict, f, indent = 4)

    global users_data
    users_data = users_dict  # Update the in-memory cache

refresh_user_data()

def fetch_and_store_data():
    # Connect to the database
    conn = connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # Execute the query to get event data
    cursor.execute("SELECT * FROM event")
    events = cursor.fetchall()
    
    # Fetch inventory data
    cursor.execute("SELECT * FROM inventory")
    inventory = cursor.fetchall()
        
    # Convert the date field to string in each event
    for event in events:
        if isinstance(event['date'], date):  # Check if 'date' field is a date object
            event['date'] = event['date'].isoformat()  # Convert date to string format
    
    # Close the connection
    cursor.close()
    conn.close()
 
    # Write the events to a JSON file
    with open('events.json', 'w') as f:
        json.dump(events, f, indent=4)

    # Write inventory data to inventory.json
    with open('inventory.json', 'w') as inventory_file:
        json.dump(inventory, inventory_file, indent=4)

def fetch_and_store_inv():
    # Connect to the database
    conn = connect(**db_config)
    cursor = conn.cursor(dictionary=True)
    
    # Fetch inventory data
    cursor.execute("SELECT * FROM inventory")
    inventory = cursor.fetchall()

    # Close the connection
    cursor.close()
    conn.close()

    # Write inventory data to inventory.json
    with open('inventory.json', 'w') as inventory_file:
        json.dump(inventory, inventory_file, indent=4)

def load_events_from_json():
    try:
        with open('events.json', 'r') as f:
            events = json.load(f)
        return events
    except FileNotFoundError:
        print("events.json file not found.")
        return []
    except json.JSONDecodeError:
        print("Error decoding events.json.")
        return []

def load_inventory_from_json():
    try:
        with open('inventory.json', 'r') as f:
            inventory = json.load(f)
        return inventory
    except FileNotFoundError:
        print("inventory.json file not found.")
        return []
    except json.JSONDecodeError:
        print("Error decoding inventory.json.")
        return []

def fetch_scheduled_event_and_details(email, events):
    try:
        # Connect to the database
        connection = connect(**db_config)
        cursor = connection.cursor()

        # Fetch the scheduled event for the given email
        query = "SELECT email, event_id FROM scheduled_events WHERE email = %s"
        cursor.execute(query, (email,))
        result = cursor.fetchone()

        # Check if the user has any scheduled events
        if result is None:
            return None

        # If user has a scheduled event, extract event_id
        email, event_id = result

        # Find the event details based on event_id
        event_details = next((event for event in events if event['event_id'] == event_id), None)

        # If event details are found, format the result as a string
        if event_details:
            result = (event_details['event_id'], event_details['name'], event_details['date'] ,event_details['place'])
            return result
        else:
            return None

    except Error:
        return None

    finally:
        # Close the cursor and the connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def fetch_requests_by_pincode_and_blood_type(pincode, blood_type):
    try:
        # Get database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # Define the query with placeholders for pincode and blood_type
        query = "SELECT request_id, quantity, urgency FROM requests WHERE pincode = %s AND blood_type = %s"
        
        # Execute the query with provided arguments
        cursor.execute(query, (pincode, blood_type))

        # Fetch all matching rows
        results = cursor.fetchall()

        # Check if any rows are returned
        if not results:
            return None
        
        # Format and return results as a list of dictionaries
        requests_data = [
            {"request_id": row[0], "quantity": row[1], "urgency": row[2]}
            for row in results
        ]
        
        return requests_data

    except Error as err:
        print(f"Error: {err}")
        return None

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def check_donation_eligibility(email):
    try:
        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # Query the last donation date for the given email
        query = "SELECT donation_date FROM donated WHERE email = %s ORDER BY donation_date DESC LIMIT 1"
        cursor.execute(query, (email,))
        result = cursor.fetchone()

        # If no record is found, user is eligible to donate immediately
        if result is None:
            return True, None  # Eligible to donate with no prior donations, so no next eligible date

        # Retrieve the last donation date
        last_donation_date = result[0]

        # Calculate the next eligible date for donation (3 months after last donation)
        next_eligible_date = last_donation_date + timedelta(days=90)

        # Check if today's date is past the next eligible date
        if date.today() >= next_eligible_date:
            return True, None  # Eligible to donate
        else:
            return False, next_eligible_date  # Not eligible; return the next eligible date

    except Error as e:
        print("Error checking donation eligibility:", e)
        return False, None

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def check_scheduled_event(email):
    try:
        # Establish database connection
        connection = get_db_connection()
        cursor = connection.cursor()

        # Query for scheduled events for the given email
        query = "SELECT event_id FROM scheduled_events WHERE email = %s"
        cursor.execute(query, (email,))
        result = cursor.fetchone()

        # If result is None, there are no scheduled events for this user
        if result is None:
            return False  # No scheduled events
        else:
            return True  # There is at least one scheduled event

    except Error as e:
        print("Error checking scheduled events:", e)
        return False

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form['fullname']
        email = request.form['email']
        password = request.form['password']
        blood_type = request.form['blood_type']
        role = request.form['role']
        pincode = request.form['pincode']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the user already exists
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            flash("Email already exists! Please log in, Life Saver")
            return redirect(url_for('login', email=email))  # Redirect to login page
        
        cursor.execute("INSERT IGNORE INTO users (full_name, email, password, blood_type, role, pincode) VALUES (%s, %s, %s, %s, %s, %s)",
            (fullname, email, password, blood_type, role, pincode))

        conn.commit()
        cursor.close()
        conn.close()
        refresh_user_data()

        flash("Registration successful!")
        return redirect(url_for('reg_confirm', email=email))

    return render_template("register.html")

@app.route("/reg_confirm")
def reg_confirm():
    email = request.args.get('email')
    user = users_data.get(email)
    return render_template("register_confirmation.html", user=user)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify login credentials and role
        cursor.execute("""SELECT * FROM users WHERE email = %s AND password = %s AND role = %s""", (email, password, role))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            user_data = {
                'fullname': user[1],
                'email': user[0],
                'blood_type': user[3],
                'pincode': user[4],
                'role': user[5]
            }
            session['user'] = user_data
            
            # Redirect based on role
            if role == 'donor':
                return redirect(url_for('dashboard', email=email))  # Donor profile + dashboard
            elif role == 'admin':
                return redirect(url_for('make_request', email=email))  # Request page for admins
            elif role == 'manager':
                return redirect(url_for('inventory', email=email))  # Inventory page for managers
        else:
            flash("Invalid login credentials or role selected!")
            return redirect(url_for('login'))

    return render_template("login.html")

@app.route("/request", methods=['GET', 'POST'])
def make_request():

    email = request.args.get('email')
    user = users_data.get(email)

    if request.method == 'POST':
        request_id = request.form['request_id']
        pincode = request.form['pincode']
        blood_type = request.form['blood_type']
        quantity = request.form['quantity']
        urgency = request.form['urgency']

        if user is None:
            flash("Error: User session parameter is missing!")
            return redirect(url_for('login'))

        # Database connection
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if request_id:
                cursor.execute("SELECT request_id FROM requests WHERE request_id = %s", (request_id,))
                if cursor.fetchone():
                    flash("Request ID already exists! Please use a unique ID.")
                    return redirect(url_for('make_request', email=email))
            
            # Insert the blood request into the database
            cursor.execute("INSERT INTO requests (request_id, pincode, blood_type, quantity, urgency) VALUES (%s, %s, %s, %s, %s)",
                            (request_id, pincode, blood_type, quantity, urgency))
            
            conn.commit()
            flash("Blood request submitted successfully!")
        except Exception as e:
            conn.rollback()
            print(f"An error occurred: {e}")
            flash("An error occurred while submitting your request.")
        finally:
            cursor.close()
            conn.close()

        # Redirect to profile page after successful request submission
        return render_template("req_conf.html")

    return render_template("request.html", email=email)

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        email = request.form.get('email')
        view = request.form.get('view')
    else:
        view = 'events'  # Default to showing events

    if request.method != 'POST':
        email = request.args.get('email')
    user = users_data.get(email)

    if user is None:
        return redirect(url_for('login'))
    
    fetch_and_store_data()
    events = load_events_from_json()
    inventory = load_inventory_from_json()
    scheduled_events = fetch_scheduled_event_and_details(email, events)
    requests = fetch_requests_by_pincode_and_blood_type(user.get('pincode'), user.get('blood_type'))

    return render_template('dashboard.html', user=user, events=events, inventory=inventory, view=view, scheduled_events=scheduled_events, alerts=requests)

@app.route('/schedule_event', methods=['POST'])
def schedule_event():
    email = request.form.get('email')
    event_id = request.form.get('event_id')
    scheduled_date = request.form.get('scheduled_date')  # Assume this is a date string

    # Check eligibility and if already scheduled
    eligible, next_eligible_date = check_donation_eligibility(email)
    already_scheduled = check_scheduled_event(email)

    # Determine the status message
    if eligible and not already_scheduled:
        try:
            # Database connection
            connection = get_db_connection()
            cursor = connection.cursor()

            # Insert the new scheduled event
            insert_query = """
            INSERT INTO scheduled_events (email, event_id, scheduled_date)
            VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (email, event_id, scheduled_date))
            connection.commit()
            status_message = "Event successfully scheduled."

        except Error as e:
            print("Error scheduling event:", e)
            status_message = "There was an error scheduling the event."
        
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    else:
        if not eligible:
            status_message = f"You’re not eligible to donate yet due to the 3-month waiting period. You’ll be eligible to donate again on {next_eligible_date}. Thank you for your patience and support!"
        elif already_scheduled:
            status_message = "You already have a scheduled event."

    # Render the status message page
    return render_template('schedule_status.html', message=status_message, email=email)

@app.route("/inventory", methods=['GET', 'POST'])
def inventory():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        blood_type = request.form['blood_type']
        units = request.form['units']
        print("post")
        try:
            print("try")
            cursor.execute("UPDATE inventory SET units = %s WHERE blood_type = %s", (units, blood_type))
            conn.commit()
            flash("Inventory updated successfully!")
            print("try done")
        except Error as err:
            print(f"Error: {err}")
            flash("Failed to update inventory.")
        finally:
            cursor.close()
            conn.close()
    
    # Retrieve and display the current inventory data
    fetch_and_store_inv()
    inventory_data = load_inventory_from_json()

    return render_template("inventory.html", inventory=inventory_data)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        # Here you would handle the password reset logic (e.g., sending an email)
        flash('If an account with that email exists, a password reset link has been sent.', 'info')
        return render_template('reset_password_success.html', email=email)
    
    return render_template('reset_password.html')

@app.route('/status')
def status():
    return render_template('status.html')  # Success message page

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)