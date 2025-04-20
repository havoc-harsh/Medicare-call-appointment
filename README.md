# Medicare Call Assistant

A voice call appointment system powered by Twilio and LLM.

## Setup Instructions

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Add your Twilio credentials, Groq API key, and database details

4. Run the application:
   ```
   python run.py
   ```

## Important Notes

- For local development with Twilio, use ngrok or another service to expose your local server
- Never commit sensitive API keys or tokens to version control
- Make sure your Twilio account has active phone numbers configured

## Features

- Voice call appointment scheduling
- Integration with Twilio for calls
- LLM-powered conversational interface
- Database integration for appointment storage 