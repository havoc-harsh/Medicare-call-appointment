import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
    
    # Groq API Configuration
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama3-70b-8192")
    
    # Database Configuration
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    
    # Application Configuration
    PORT = int(os.environ.get("PORT", 5001))
    DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "call_log.txt")
    
    # Available Hospitals (for demo)
    HOSPITALS = {
        1: "Medicare General Hospital",
        2: "City Medical Center",
        3: "Community Health Hospital"
    } 