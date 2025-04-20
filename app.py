from flask import Flask, render_template, request, jsonify
import os
import logging
from api.routes import api
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=Config.LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("app")

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management

# Register blueprints
app.register_blueprint(api, url_prefix='/api')

@app.route('/')
def index():
    """Homepage with a form to initiate a call"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Medicare Appointment Booking System</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                padding: 20px;
                max-width: 800px;
                margin: 0 auto;
                color: #333;
            }
            h1 {
                color: #2a5298;
                border-bottom: 2px solid #eee;
                padding-bottom: 10px;
            }
            .form-group {
                margin-bottom: 15px;
            }
            label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
            }
            input[type="text"] {
                width: 100%;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 16px;
            }
            button {
                background-color: #2a5298;
                color: white;
                border: none;
                padding: 10px 15px;
                font-size: 16px;
                cursor: pointer;
                border-radius: 4px;
            }
            button:hover {
                background-color: #1d3c6a;
            }
            #result {
                margin-top: 20px;
                padding: 15px;
                border-radius: 4px;
                display: none;
            }
            .success {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
            }
            .error {
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
            }
        </style>
    </head>
    <body>
        <h1>Medicare Appointment Booking System</h1>
        <p>Use this form to initiate an outbound call to a patient for appointment booking.</p>
        
        <div class="form-group">
            <label for="phone">Patient Phone Number:</label>
            <input type="text" id="phone" placeholder="e.g., +1234567890" autocomplete="tel">
            <small>Please include country code (e.g., +1 for US, +91 for India)</small>
        </div>
        
        <button onclick="initiateCall()">Call Patient</button>
        
        <div id="result"></div>
        
        <script>
            function initiateCall() {
                const phone = document.getElementById('phone').value.trim();
                const resultDiv = document.getElementById('result');
                
                // Basic validation
                if (!phone) {
                    resultDiv.className = 'error';
                    resultDiv.textContent = 'Please enter a phone number';
                    resultDiv.style.display = 'block';
                    return;
                }
                
                // Show loading state
                resultDiv.className = '';
                resultDiv.textContent = 'Initiating call...';
                resultDiv.style.display = 'block';
                
                // Send API request
                fetch('/api/call', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ phone: phone })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        resultDiv.className = 'success';
                        resultDiv.textContent = `Call initiated successfully! Call ID: ${data.call_sid}`;
                    } else {
                        resultDiv.className = 'error';
                        resultDiv.textContent = `Error: ${data.error}`;
                    }
                })
                .catch(error => {
                    resultDiv.className = 'error';
                    resultDiv.textContent = `An error occurred: ${error.message}`;
                });
            }
        </script>
    </body>
    </html>
    """

@app.route('/status')
def status():
    """Simple status endpoint"""
    return jsonify({
        'status': 'running',
        'twilio': {
            'account_sid': Config.TWILIO_ACCOUNT_SID[:6] + '...',  # Show only first 6 chars for security
            'phone_number': Config.TWILIO_PHONE_NUMBER
        },
        'database': Config.DATABASE_URL.split('@')[1] if '@' in Config.DATABASE_URL else 'configured'
    })

if __name__ == '__main__':
    logger.info(f"Starting Medicare Call System on port {Config.PORT}")
    app.run(host='0.0.0.0', port=Config.PORT, debug=Config.DEBUG) 