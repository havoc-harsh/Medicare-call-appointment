#!/usr/bin/env python

"""
Medicare Call System Launcher
This script starts the Flask application for the Medicare appointment booking call system.
"""

from app import app
import logging
import os
import sys
from config import Config

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=Config.LOG_FILE,
        filemode='a'
    )
    logger = logging.getLogger("runner")
    
    # Check for manually provided ngrok URL
    if len(sys.argv) > 1:
        public_url = sys.argv[1]
        if not public_url.startswith('http'):
            public_url = 'https://' + public_url
    else:
        logger.warning("No ngrok URL provided. Using local URL (won't work with Twilio)")
        public_url = f"http://localhost:{Config.PORT}"
    
    # Set the environment variable for the API
    os.environ['PUBLIC_URL'] = public_url
    
    # Log startup information
    logger.info("="*80)
    logger.info("Starting Medicare Call Appointment System")
    logger.info(f"Twilio Phone Number: {Config.TWILIO_PHONE_NUMBER}")
    logger.info(f"Public URL: {public_url}")
    logger.info(f"Database: {Config.DATABASE_URL.split('@')[1] if '@' in Config.DATABASE_URL else 'configured'}")
    logger.info(f"Running on port: {Config.PORT}")
    logger.info(f"Debug mode: {Config.DEBUG}")
    logger.info("="*80)
    
    # Run the application
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG) 