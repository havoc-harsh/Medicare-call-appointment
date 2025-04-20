import psycopg2
import psycopg2.extras
import datetime
from dateutil import parser
import logging
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=Config.LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("database_service")

class DatabaseService:
    def __init__(self):
        self.connection_string = Config.DATABASE_URL
        logger.info("Database service initialized")
    
    def get_connection(self):
        """Create a connection to the PostgreSQL database"""
        try:
            connection = psycopg2.connect(self.connection_string)
            return connection
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

    def check_hospital_exists(self, hospital_id):
        """Check if a hospital exists in the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
            SELECT "id", "name" FROM "Hospital" WHERE "id" = %s
            """
            
            cursor.execute(query, (hospital_id,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return result is not None, result[1] if result else None
        except Exception as e:
            logger.error(f"Error checking hospital existence: {e}")
            return False, None

    def find_doctor_by_name_or_specialty(self, name_or_specialty, hospital_id=None):
        """Find a doctor by name or specialty"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if hospital_id:
                query = """
                SELECT "id", "name", "specialization" FROM "Doctor" 
                WHERE (LOWER("name") LIKE %s OR LOWER("specialization") LIKE %s) AND "hospitalId" = %s
                LIMIT 1
                """
                cursor.execute(query, (f"%{name_or_specialty.lower()}%", f"%{name_or_specialty.lower()}%", hospital_id))
            else:
                query = """
                SELECT "id", "name", "specialization", "hospitalId" FROM "Doctor" 
                WHERE LOWER("name") LIKE %s OR LOWER("specialization") LIKE %s
                LIMIT 1
                """
                cursor.execute(query, (f"%{name_or_specialty.lower()}%", f"%{name_or_specialty.lower()}%"))
            
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                doctor_info = {
                    "id": result[0],
                    "name": result[1],
                    "specialization": result[2]
                }
                if not hospital_id:
                    doctor_info["hospitalId"] = result[3]
                return True, doctor_info
            return False, None
        except Exception as e:
            logger.error(f"Error finding doctor: {e}")
            return False, None

    def check_appointment_availability(self, hospital_id, date, time):
        """Check if there are any conflicting appointments at the specified time"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            date_obj = date if isinstance(date, datetime.date) else parser.parse(date).date()
            
            query = """
            SELECT COUNT(*) FROM "Appointment" 
            WHERE "hospitalId" = %s AND "date" = %s AND "time" = %s
            """
            
            cursor.execute(query, (hospital_id, date_obj, time))
            count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            # If there are less than 3 appointments at the same time, it's available
            return count < 3
        except Exception as e:
            logger.error(f"Error checking appointment availability: {e}")
            return False

    def create_appointment(self, appointment_data):
        """Create a new appointment in the database"""
        try:
            # Parse the date if it's a string
            if isinstance(appointment_data['date'], str):
                date_obj = parser.parse(appointment_data['date']).date()
            else:
                date_obj = appointment_data['date']
            
            # Connect to the database
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            # Insert the appointment
            query = """
            INSERT INTO "Appointment" (
                "patient", "phone", "symptoms", "latitude", "longitude", "date", "time", 
                "hospitalId", "alert"
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id;
            """
            
            # Default values for fields not collected via call
            latitude = appointment_data.get('latitude', 0.0)
            longitude = appointment_data.get('longitude', 0.0)
            alert = appointment_data.get('alert', [])
            
            cursor.execute(
                query,
                (
                    appointment_data['patient'],          # patient name
                    appointment_data['phone'],            # phone
                    appointment_data['symptoms'],         # symptoms
                    latitude,                             # latitude
                    longitude,                            # longitude
                    date_obj,                             # date
                    appointment_data['time'],             # time
                    int(appointment_data['hospital_id']), # hospitalId
                    alert                                 # alert
                )
            )
            
            # Get the appointment ID
            appointment_id = cursor.fetchone()[0]
            
            # Commit the transaction
            conn.commit()
            
            # Close the connection
            cursor.close()
            conn.close()
            
            logger.info(f"Created appointment {appointment_id} for {appointment_data['patient']} at hospital {appointment_data['hospital_id']} on {date_obj} {appointment_data['time']}")
            return appointment_id
            
        except Exception as e:
            logger.error(f"Error creating appointment: {e}")
            return None
    
    def find_user_by_phone(self, phone):
        """Find a user by phone number"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # First, check if the phone number exists in the MedicalProfile
            query = """
            SELECT mp."userId", u."name" FROM "MedicalProfile" mp
            JOIN "User" u ON mp."userId" = u."id"
            WHERE mp."phone" = %s
            """
            
            cursor.execute(query, (phone,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return True, {"id": result[0], "name": result[1]}
            return False, None
        except Exception as e:
            logger.error(f"Error finding user by phone: {e}")
            return False, None 