from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import os
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=Config.LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("twilio_service")

class TwilioService:
    def __init__(self):
        self.account_sid = Config.TWILIO_ACCOUNT_SID
        self.auth_token = Config.TWILIO_AUTH_TOKEN
        self.phone_number = Config.TWILIO_PHONE_NUMBER
        self.client = Client(self.account_sid, self.auth_token)
        self.public_url = os.environ.get('PUBLIC_URL', '')
        logger.info("Twilio service initialized")
    
    def _get_full_url(self, path):
        """Convert a relative path to a full URL with the public domain"""
        if not path.startswith('/'):
            path = '/' + path
        
        if self.public_url:
            # Use the public URL for webhooks
            return f"{self.public_url}{path}"
        else:
            # Fallback to relative URL (won't work with Twilio)
            return path
    
    def make_call(self, to_number, callback_url):
        """
        Initiate a call to a specific phone number
        Returns the call SID if successful
        """
        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                url=callback_url,
                record=True
            )
            logger.info(f"Initiated call to {to_number}, SID: {call.sid}")
            return call.sid
        except Exception as e:
            logger.error(f"Error making call: {e}")
            return None
    
    def send_sms(self, to_number, message):
        """
        Send an SMS to a specific phone number
        Returns the message SID if successful
        """
        try:
            sms = self.client.messages.create(
                to=to_number,
                from_=self.phone_number,
                body=message
            )
            logger.info(f"Sent SMS to {to_number}, SID: {sms.sid}")
            return sms.sid
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return None
    
    def create_welcome_response(self):
        """
        Create a TwiML response for the initial call greeting
        """
        response = VoiceResponse()
        response.say("Hello! This is Medicare's appointment booking system. I need to collect some specific information to book your appointment.")
        
        # Use full URL for the action
        action_url = self._get_full_url('/api/conversation')
        logger.info(f"Welcome response using action URL: {action_url}")
        
        gather = Gather(
            input='speech',
            action=action_url,
            method='POST',
            timeout=10,              # Increased timeout
            speech_timeout='auto',
            language='en-US',
            enhanced=True,           # Use enhanced speech recognition
            speechModel='phone_call'  # Optimize for phone calls
        )
        gather.say("Please clearly state your full name, hospital ID, symptoms, appointment date, and appointment time. For example, say: My name is John Smith, hospital ID 1, symptoms are headache, date 2023-06-15, time 10:00 AM.")
        
        response.append(gather)
        
        # If no input received
        response.say("I didn't hear anything. Please call back when you're ready to book an appointment.")
        response.hangup()
        
        return response
    
    def create_conversation_response(self, text_to_say, action_url=None, gather_speech=True):
        """
        Create a TwiML response for continuing the conversation
        """
        response = VoiceResponse()
        
        # Use full URL for the action
        if action_url:
            action_url = self._get_full_url(action_url)
        else:
            action_url = self._get_full_url('/api/conversation')
        
        logger.info(f"Conversation response using action URL: {action_url}")
        
        if gather_speech:
            gather = Gather(
                input='speech',
                action=action_url,
                method='POST',
                timeout=10,              # Increased timeout
                speech_timeout='auto',
                language='en-US',
                enhanced=True,           # Use enhanced speech recognition 
                speechModel='phone_call'  # Optimize for phone calls
            )
            gather.say(text_to_say)
            response.append(gather)
            
            # If no input received after gather
            response.say("I didn't hear anything. Please call back when you're ready.")
            response.hangup()
        else:
            # Just say the text without gathering a response
            response.say(text_to_say)
            
            if action_url:
                response.redirect(action_url)
            else:
                response.hangup()
        
        return response
    
    def create_confirmation_response(self, confirmation_text, appointment_id=None):
        """
        Create a TwiML response for confirming an appointment
        """
        response = VoiceResponse()
        
        response.say(confirmation_text)
        
        # If we have an appointment ID, offer to send details via SMS
        if appointment_id:
            # Use full URL for the action
            action_url = self._get_full_url(f'/api/send_confirmation?appointment_id={appointment_id}')
            logger.info(f"Confirmation response using action URL: {action_url}")
            
            gather = Gather(
                input='speech',
                action=action_url,
                method='POST',
                timeout=5,
                speech_timeout='auto'
            )
            gather.say("Would you like me to send these details to you via text message? Say yes or no.")
            response.append(gather)
            
            # If no response
            response.say("I'll take that as a no. Your appointment has been confirmed. Thank you for calling Medicare.")
            response.hangup()
        else:
            response.say("Thank you for calling Medicare. Goodbye!")
            response.hangup()
        
        return response
    
    def get_caller_number(self, request):
        """Extract the caller's phone number from the Twilio request"""
        return request.values.get('From', '')
    
    def get_speech_result(self, request):
        """Extract the speech transcription from the Twilio request"""
        # Log all relevant request values for debugging
        logger.info(f"REQUEST DATA: {dict(request.values)}")
        
        speech_result = request.values.get('SpeechResult', '')
        confidence = request.values.get('Confidence', '0')
        
        logger.info(f"SPEECH RECOGNITION: '{speech_result}' (confidence: {confidence})")
        
        # If empty or very low confidence, provide more details in logs
        if not speech_result:
            logger.warning(f"NO SPEECH RECOGNIZED. Raw request values: {dict(request.values)}")
            return "I couldn't hear what you said. Please try speaking again clearly."
        elif confidence and float(confidence) < 0.3:
            logger.warning(f"LOW CONFIDENCE SPEECH: {confidence}. '{speech_result}'")
            return "I heard you, but wasn't very confident. Could you please speak more clearly and try again?"
            
        return speech_result 