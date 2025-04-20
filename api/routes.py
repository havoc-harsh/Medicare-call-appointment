from flask import Blueprint, request, session, url_for
import logging
import json
from services.twilio import TwilioService
from services.llm import LLMService
from services.database import DatabaseService
from config import Config
import os
import re

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=Config.LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("api_routes")

# Initialize blueprint
api = Blueprint('api', __name__)

# Initialize services
twilio_service = TwilioService()
llm_service = LLMService()
db_service = DatabaseService()

# Session data storage - in production, use Redis or another persistent store
conversation_history = {}

@api.route('/call', methods=['POST'])
def initiate_call():
    """
    Endpoint to initiate an outbound call to a patient
    Expects 'phone' parameter in the request
    """
    try:
        # Get the phone number from the request
        phone = request.json.get('phone')
        if not phone:
            return {'error': 'Phone number is required'}, 400
        
        # Normalize phone number if needed
        if not phone.startswith('+'):
            phone = f"+{phone}"
        
        # Generate the callback URL for when the call is answered
        # Use the public URL from environment instead of a hardcoded webhook
        public_url = os.environ.get('PUBLIC_URL', '')
        if public_url:
            callback_url = f"{public_url}/api/welcome"
        else:
            # Fallback to local URL (won't work with Twilio)
            callback_url = url_for('api.welcome', _external=True)
        
        logger.info(f"Using callback URL: {callback_url}")
        
        # Initiate the call
        call_sid = twilio_service.make_call(phone, callback_url)
        
        if call_sid:
            # Initialize conversation history for this call
            conversation_history[call_sid] = []
            
            return {
                'success': True,
                'message': 'Call initiated successfully',
                'call_sid': call_sid
            }
        else:
            return {'error': 'Failed to initiate call'}, 500
            
    except Exception as e:
        logger.error(f"Error initiating call: {e}")
        return {'error': str(e)}, 500

@api.route('/welcome', methods=['POST'])
def welcome():
    """
    Initial webhook when a call is answered
    """
    try:
        # Get call SID
        call_sid = request.values.get('CallSid')
        logger.info(f"Call answered: {call_sid}")
        
        # Initialize conversation history if not exists
        if call_sid not in conversation_history:
            conversation_history[call_sid] = []
        
        # Create welcome TwiML
        response = twilio_service.create_welcome_response()
        return str(response)
    
    except Exception as e:
        logger.error(f"Error in welcome: {e}")
        # Return a simple response in case of error
        response = twilio_service.create_conversation_response(
            "I'm sorry, we're experiencing technical difficulties. Please try again later.",
            gather_speech=False
        )
        return str(response)

@api.route('/conversation', methods=['POST'])
def conversation():
    """
    Main webhook for handling conversation turns
    """
    try:
        # Get call SID and speech result
        call_sid = request.values.get('CallSid')
        speech_result = twilio_service.get_speech_result(request)
        
        # Get the CALLED number (recipient), not the caller number (which is Twilio)
        recipient_number = request.values.get('To', '+919955433033')  # Default to your number if not found
        caller_number = twilio_service.get_caller_number(request)
        
        logger.info(f"PROCESSING CONVERSATION to {recipient_number} from {caller_number}: '{speech_result}'")
        
        # Initialize or get conversation history
        if call_sid not in conversation_history:
            conversation_history[call_sid] = []
        
        # Add user's speech to history
        conversation_history[call_sid].append({"role": "user", "content": speech_result})
        
        # Get appointment data from conversation history
        appointment_data = session.get(f"appointment_data_{call_sid}", {})
        
        # Add recipient phone number, not Twilio's number
        if 'phone' not in appointment_data:
            appointment_data['phone'] = recipient_number
            logger.info(f"Added recipient phone number: {recipient_number}")
        
        # DIRECT CAPTURE: Check for specific patterns in speech to directly extract information
        speech_lower = speech_result.lower()
        
        # Name extraction - improved patterns
        name_captured = False
        name_patterns = [
            r"(?:my name is|this is|i am|i'm|name is) ([A-Za-z\s]+)", 
            r"([A-Za-z\s]+) (?:is my name)",
            r"patient(?:'s)? name (?:is)? ([A-Za-z\s]+)",
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, speech_lower)
            if match:
                raw_name = match.group(1).strip()
                # Clean up the name - remove words like "calling", "here", etc.
                clean_words = [word for word in raw_name.split() if word not in ['calling', 'here', 'speaking', 'and', 'the', 'to', 'for', 'with', 'hospital', 'id', 'symptoms', 'date', 'time']]
                if clean_words:
                    name = ' '.join(clean_words).title()
                    logger.info(f"DIRECT NAME CAPTURE: Found name '{name}' using pattern '{pattern}'")
                    appointment_data['patient'] = name
                    name_captured = True
                    break
        
        # If no name captured and the entire speech is short (likely just a name), use it as name
        if not name_captured and len(speech_lower.split()) <= 4 and all(word.isalpha() for word in speech_lower.split()):
            if not any(keyword in speech_lower for keyword in ['hospital', 'symptom', 'date', 'time', 'appointment', 'book']):
                name = speech_result.strip().title()
                logger.info(f"DIRECT NAME CAPTURE: Using entire short response as name: '{name}'")
                appointment_data['patient'] = name
                
        # Hospital ID extraction - improved patterns
        hospital_patterns = [
            r"hospital (?:id|ID|number|#)?\s*(?:is)?\s*(\d+)",
            r"hospital(?:id|ID)? (\d+)",
            r"(?:id|ID|number) (\d+)",
            r"hospital (\d+)",
            r"the number (\d+)"
        ]
        
        for pattern in hospital_patterns:
            match = re.search(pattern, speech_lower)
            if match:
                hospital_id = match.group(1).strip()
                logger.info(f"DIRECT HOSPITAL CAPTURE: Found hospital ID '{hospital_id}' using pattern '{pattern}'")
                try:
                    appointment_data['hospital_id'] = int(hospital_id)
                    break
                except ValueError:
                    logger.warning(f"Invalid hospital ID format: {hospital_id}")
        
        # Date extraction
        date_patterns = [
            r"date (?:is|of)? (20\d\d-\d{1,2}-\d{1,2})",
            r"(20\d\d-\d{1,2}-\d{1,2})",
            r"date (?:is|of)? (\d{1,2}[/-]\d{1,2}[/-]20\d\d)",
            r"(\d{1,2}[/-]\d{1,2}[/-]20\d\d)",
            r"date (?:is|for|on)? ([a-z]+ \d{1,2}(?:st|nd|rd|th)?(?:,)? 20\d\d)",
            r"on ([a-z]+ \d{1,2}(?:st|nd|rd|th)?(?:,)? 20\d\d)"
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, speech_lower)
            if match:
                date_str = match.group(1).strip()
                logger.info(f"DIRECT DATE CAPTURE: Found date '{date_str}' using pattern '{pattern}'")
                appointment_data['date'] = date_str
                break
        
        # Time extraction
        time_patterns = [
            r"time (?:is|at)? (\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"at (\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"time (?:is|at)? (\d{1,2}(?::\d{2})?\s*(?:in the morning|in the afternoon|in the evening))",
            r"(\d{1,2}) (?:o'clock|oclock)"
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, speech_lower)
            if match:
                time_str = match.group(1).strip()
                logger.info(f"DIRECT TIME CAPTURE: Found time '{time_str}' using pattern '{pattern}'")
                appointment_data['time'] = time_str
                break
                
        # Symptoms extraction - expanded approach
        symptoms_captured = False
        
        # Check for explicit symptom markers
        if any(marker in speech_lower for marker in ["symptom", "problem", "issue", "reason", "suffering", "pain", "appointment for"]):
            symptoms_patterns = [
                r"symptom(?:s)? (?:is|are) (.+?)(?:\.|$|date|time|hospital)",
                r"problem(?:s)? (?:is|are) (.+?)(?:\.|$|date|time|hospital)",
                r"suffering from (.+?)(?:\.|$|date|time|hospital)",
                r"reason (?:is|for) (.+?)(?:\.|$|date|time|hospital)",
                r"issue (?:is|with) (.+?)(?:\.|$|date|time|hospital)",
                r"appointment for (.+?)(?:\.|$|date|time|hospital)",
                r"i have (?:a|an) (.+?)(?:\.|$|date|time|hospital)"
            ]
            
            for pattern in symptoms_patterns:
                match = re.search(pattern, speech_lower)
                if match:
                    symptoms = match.group(1).strip()
                    logger.info(f"DIRECT SYMPTOMS CAPTURE: Found symptoms '{symptoms}' using pattern '{pattern}'")
                    appointment_data['symptoms'] = symptoms
                    symptoms_captured = True
                    break
        
        # If we've already captured name, hospital, date, and time but no symptoms, 
        # and there's remaining text not accounted for, use it as symptoms
        if not symptoms_captured and 'patient' in appointment_data and 'hospital_id' in appointment_data and 'date' in appointment_data and 'time' in appointment_data:
            # Try to extract any remaining content as symptoms
            words_to_remove = []
            if 'patient' in appointment_data:
                words_to_remove.extend(appointment_data['patient'].lower().split())
            if 'hospital_id' in appointment_data:
                words_to_remove.extend([f"hospital {appointment_data['hospital_id']}", f"hospital id {appointment_data['hospital_id']}"])
            if 'date' in appointment_data:
                words_to_remove.append(str(appointment_data['date']).lower())
            if 'time' in appointment_data:
                words_to_remove.append(str(appointment_data['time']).lower())
                
            # Also remove common phrases
            common_phrases = ["my name is", "this is", "i am", "i'm", "name is", "hospital id", "date is", "time is",
                             "i need", "i want", "to book", "an appointment", "appointment for"]
            words_to_remove.extend(common_phrases)
            
            # Remove these words from the speech
            remaining_text = speech_lower
            for phrase in words_to_remove:
                remaining_text = remaining_text.replace(phrase, " ")
                
            # Clean up the remaining text
            remaining_text = ' '.join(remaining_text.split())
            if len(remaining_text) > 3:  # If we have something substantial left
                logger.info(f"INDIRECT SYMPTOMS CAPTURE: Using remaining text as symptoms: '{remaining_text}'")
                appointment_data['symptoms'] = remaining_text.capitalize()
        
        # Process with LLM for anything we didn't directly capture
        extracted_data = llm_service.extract_appointment_data(
            speech_result, 
            conversation_history[call_sid]
        )
        
        # Update appointment data with any new information from LLM
        for key, value in extracted_data.items():
            if value is not None and value != "":
                # Special handling for patient name
                if key == 'patient':
                    # Don't set patient to a string "null"
                    if value == "null" or value == "NULL" or value == "None":
                        continue
                    # Only update if the new name is more complete (longer) or we don't have a name yet
                    if key not in appointment_data or not appointment_data[key] or appointment_data[key] == "null" or len(value) > len(appointment_data[key]):
                        logger.info(f"LLM NAME UPDATE: Updating patient name from '{appointment_data.get(key, '')}' to '{value}'")
                        appointment_data[key] = value
                else:
                    if key not in appointment_data or not appointment_data[key]:
                        logger.info(f"LLM DATA UPDATE: Setting {key} to '{value}'")
                        appointment_data[key] = value
                    else:
                        logger.info(f"LLM DATA UPDATE: Keeping existing {key}: '{appointment_data[key]}' (LLM suggested: '{value}')")
        
        # Log the appointment data for debugging
        logger.info(f"CURRENT APPOINTMENT DATA: {appointment_data}")
        
        # Store updated appointment data in session
        session[f"appointment_data_{call_sid}"] = appointment_data
        
        # Check if we have all required fields
        required_fields = ['patient', 'symptoms', 'date', 'time', 'hospital_id']
        missing_fields = [field for field in required_fields if field not in appointment_data or not appointment_data[field]]
        
        logger.info(f"MISSING FIELDS: {missing_fields}")
        
        if not missing_fields:
            # We have all required information, proceed to confirmation
            
            # Verify hospital exists
            hospital_exists, hospital_name = db_service.check_hospital_exists(int(appointment_data['hospital_id']))
            if not hospital_exists:
                # If hospital doesn't exist, ask for a different one
                response_text = f"I'm sorry, the hospital with ID {appointment_data['hospital_id']} doesn't exist in our system. Please say a different hospital ID between 1 and 10."
                appointment_data.pop('hospital_id', None)  # Remove invalid hospital
                session[f"appointment_data_{call_sid}"] = appointment_data
                
                response = twilio_service.create_conversation_response(response_text)
                return str(response)
            
            # Check appointment availability
            is_available = db_service.check_appointment_availability(
                int(appointment_data['hospital_id']),
                appointment_data['date'],
                appointment_data['time']
            )
            
            if not is_available:
                # Suggest a different time
                response_text = f"I'm sorry, but the time slot at {appointment_data['time']} on {appointment_data['date']} is fully booked. Please suggest a different time."
                appointment_data.pop('time', None)  # Remove unavailable time
                session[f"appointment_data_{call_sid}"] = appointment_data
                
                response = twilio_service.create_conversation_response(response_text)
                return str(response)
            
            # All checks passed, generate confirmation
            confirmation_text = llm_service.verify_appointment_details(appointment_data, hospital_name)
            
            # Save confirmation state
            session[f"confirmation_state_{call_sid}"] = True
            
            # Create confirmation response
            response = twilio_service.create_conversation_response(
                confirmation_text,
                action_url='/api/confirm_appointment'
            )
            return str(response)
        else:
            # Construct a specific follow-up question based on what's missing
            if len(missing_fields) == 1:
                field = missing_fields[0]
                if field == 'patient':
                    follow_up = "I still need your full name. Please clearly say: My name is followed by your full name."
                elif field == 'hospital_id':
                    follow_up = "I need the hospital ID number. Please clearly say: Hospital ID followed by a number between 1 and 10."
                elif field == 'symptoms':
                    follow_up = "I need to know why you're booking this appointment. Please clearly say: My symptoms are, followed by your health concern."
                elif field == 'date':
                    follow_up = "I need the date for your appointment. Please clearly say: The date is, followed by a date like 2023-06-15."
                elif field == 'time':
                    follow_up = "I need the time for your appointment. Please clearly say: The time is, followed by a time like 10:00 AM."
            else:
                # Multiple fields missing
                follow_up = f"I still need your {', '.join(missing_fields[:-1])} and {missing_fields[-1]}. Please provide this information."
            
            # Add system response to history
            conversation_history[call_sid].append({"role": "assistant", "content": follow_up})
            
            # Create response
            response = twilio_service.create_conversation_response(follow_up)
            return str(response)
    
    except Exception as e:
        logger.error(f"Error in conversation: {e}")
        # Return a simple response in case of error
        response = twilio_service.create_conversation_response(
            "I'm sorry, I didn't understand that. Could you please try again?",
            gather_speech=True
        )
        return str(response)

@api.route('/confirm_appointment', methods=['POST'])
def confirm_appointment():
    """
    Webhook for handling appointment confirmation
    """
    try:
        # Get call SID and speech result
        call_sid = request.values.get('CallSid')
        speech_result = twilio_service.get_speech_result(request)
        recipient_number = request.values.get('To', '+919955433033')  # Default to your number
        caller_number = twilio_service.get_caller_number(request)
        
        logger.info(f"Confirmation to {recipient_number} from {caller_number}: '{speech_result}'")
        
        # Get appointment data from session
        appointment_data = session.get(f"appointment_data_{call_sid}", {})
        
        # Ensure we have the correct recipient phone number
        if 'phone' not in appointment_data or not appointment_data['phone'] or appointment_data['phone'] == caller_number:
            appointment_data['phone'] = recipient_number
            logger.info(f"Updated recipient phone number to: {recipient_number}")

        # Check if there's no appointment data
        if not appointment_data:
            logger.error(f"No appointment data found for call {call_sid}")
            response = twilio_service.create_conversation_response(
                "I'm sorry, we seem to have lost your appointment information. Let's start over. What appointment would you like to book?",
                action_url='/api/conversation'
            )
            return str(response)
        
        # Analyze the user's response
        response_analysis = llm_service.analyze_user_response(speech_result)
        
        if response_analysis.get('response_type') == 'confirm':
            # User confirmed the appointment
            try:
                # Create the appointment in the database
                appointment_id = db_service.create_appointment(appointment_data)
                
                if appointment_id:
                    # Send a confirmation message
                    confirmation_message = f"Great! Your appointment has been confirmed. Your appointment ID is {appointment_id}."
                    
                    # Always send an SMS confirmation to the recipient number
                    hospital_name = db_service.check_hospital_exists(int(appointment_data.get('hospital_id')))[1]
                    sms_message = f"Medicare Appointment Confirmation\nPatient: {appointment_data.get('patient')}\nDate: {appointment_data.get('date')}\nTime: {appointment_data.get('time')}\nHospital: {hospital_name}\nSymptoms: {appointment_data.get('symptoms')}\nAppointment ID: {appointment_id}"
                    
                    logger.info(f"Sending confirmation SMS to {appointment_data['phone']}")
                    twilio_service.send_sms(appointment_data['phone'], sms_message)
                    
                    response = twilio_service.create_conversation_response(
                        confirmation_message + " I've also sent you a text message with the details. Thank you for using Medicare's appointment booking service!",
                        gather_speech=False
                    )
                    
                    # Clear the session data
                    session.pop(f"appointment_data_{call_sid}", None)
                    session.pop(f"confirmation_state_{call_sid}", None)
                    
                    return str(response)
                else:
                    # Failed to create appointment
                    response = twilio_service.create_conversation_response(
                        "I'm sorry, there was a problem creating your appointment. Please try again later or call our office directly.",
                        gather_speech=False
                    )
                    return str(response)
            
            except Exception as e:
                logger.error(f"Error creating appointment: {e}")
                response = twilio_service.create_conversation_response(
                    "I'm sorry, there was a problem creating your appointment. Please try again later or call our office directly.",
                    gather_speech=False
                )
                return str(response)
                
        elif response_analysis.get('response_type') == 'correct':
            # User wants to make corrections
            response = twilio_service.create_conversation_response(
                "I understand you want to make changes. What would you like to update about your appointment?",
                action_url='/api/conversation'
            )
            
            # Reset confirmation state
            session.pop(f"confirmation_state_{call_sid}", None)
            
            return str(response)
            
        elif response_analysis.get('response_type') == 'cancel':
            # User wants to cancel
            response = twilio_service.create_conversation_response(
                "I understand you want to cancel. Your appointment has not been booked. Thank you for calling Medicare.",
                gather_speech=False
            )
            
            # Clear the session data
            session.pop(f"appointment_data_{call_sid}", None)
            session.pop(f"confirmation_state_{call_sid}", None)
            
            return str(response)
            
        else:
            # Unclear response, ask again
            response = twilio_service.create_conversation_response(
                "I'm sorry, I didn't understand your response. Please say 'yes' to confirm the appointment, 'no' to make changes, or 'cancel' to cancel.",
                action_url='/api/confirm_appointment'
            )
            return str(response)
    
    except Exception as e:
        logger.error(f"Error in confirm_appointment: {e}")
        response = twilio_service.create_conversation_response(
            "I'm sorry, we're experiencing technical difficulties. Please try again later.",
            gather_speech=False
        )
        return str(response)

@api.route('/call_status', methods=['POST'])
def call_status():
    """
    Webhook for call status updates
    """
    try:
        call_sid = request.values.get('CallSid')
        call_status = request.values.get('CallStatus')
        
        logger.info(f"Call {call_sid} status: {call_status}")
        
        # If call completed or failed, clean up session data
        if call_status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
            if call_sid in conversation_history:
                del conversation_history[call_sid]
            session.pop(f"appointment_data_{call_sid}", None)
            session.pop(f"confirmation_state_{call_sid}", None)
        
        return '', 200
    except Exception as e:
        logger.error(f"Error in call_status: {e}")
        return '', 200 