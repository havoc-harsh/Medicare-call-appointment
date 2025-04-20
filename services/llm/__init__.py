import groq
import json
import logging
from config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=Config.LOG_FILE,
    filemode='a'
)
logger = logging.getLogger("llm_service")

class LLMService:
    def __init__(self):
        self.api_key = Config.GROQ_API_KEY
        self.model = Config.GROQ_MODEL
        self.client = groq.Client(api_key=self.api_key)
        logger.info("LLM service initialized")
    
    def _call_llm(self, messages, system_prompt=None):
        """Make a call to the Groq API with the provided messages"""
        try:
            full_messages = []
            
            # Add system prompt if provided
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            
            # Add the rest of the messages
            full_messages.extend(messages)
            
            # Call the API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                temperature=0.2,  # Low temperature for more deterministic responses
                max_tokens=1024,
                top_p=0.9
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None
    
    def extract_appointment_data(self, user_input, conversation_history):
        """
        Extract appointment data from the user's input and conversation history
        Returns a dictionary with the extracted appointment details
        """
        system_prompt = """
        You are an AI assistant for a healthcare appointment booking system.
        Extract ONLY the following information from the user's input and conversation history:
        - patient: The patient's full name (only extract the person's name, not titles or descriptions)
        - symptoms: The reason for the appointment or symptoms
        - date: The appointment date (in format YYYY-MM-DD)
        - time: The appointment time (e.g., "10:00 AM")
        - hospitalId: The ID of the hospital as an integer number
        
        IMPORTANT INSTRUCTIONS:
        1. Respond in JSON format with these fields. Use null for missing fields.
        2. For hospitalId, extract ONLY the numeric ID value. Return it as a number, not a string.
        3. For patient name, extract ONLY the person's name. Do not include words like "calling" or "speaking".
        4. If you're uncertain about any field, set it to null rather than guessing.
        5. Do NOT extract any other fields. The phone number will be automatically captured.
        6. For date, convert any date formats to YYYY-MM-DD.
        7. For time, standardize to a format like "10:00 AM" or "2:30 PM".
        
        EXAMPLES:
        Input: "My name is John Smith, I need an appointment for hospital 3 on 2023-05-15 at 10:00 AM for headache"
        Output: {"patient": "John Smith", "hospitalId": 3, "date": "2023-05-15", "time": "10:00 AM", "symptoms": "headache"}
        
        Input: "I'm Sarah Johnson calling"
        Output: {"patient": "Sarah Johnson", "hospitalId": null, "date": null, "time": null, "symptoms": null}
        
        Input: "hospital id is 5"
        Output: {"patient": null, "hospitalId": 5, "date": null, "time": null, "symptoms": null}
        """
        
        try:
            # Create a single combined message with all relevant context
            combined_history = ""
            for msg in conversation_history:
                combined_history += f"{msg['role']}: {msg['content']}\n"
                
            combined_message = f"""
            Conversation history:
            {combined_history}
            
            Current input: {user_input}
            
            Extract the appointment information from the above conversation.
            """
            
            # Make a call to the LLM with clear explicit instructions
            messages = [{"role": "user", "content": combined_message}]
            
            # Call LLM twice to verify results
            response1 = self._call_llm(messages, system_prompt)
            response2 = self._call_llm(messages, system_prompt)
            
            logger.info(f"LLM EXTRACTION RESULT 1: {response1}")
            logger.info(f"LLM EXTRACTION RESULT 2: {response2}")
            
            # Parse the first response
            try:
                data = json.loads(response1)
                
                # Validate that we have a dictionary with the expected fields
                expected_fields = ['patient', 'symptoms', 'date', 'time', 'hospitalId']
                for field in expected_fields:
                    if field not in data:
                        data[field] = None
                    elif data[field] == "":
                        data[field] = None
                        
                # Try to validate with second response if available
                if response2:
                    try:
                        data2 = json.loads(response2)
                        # If fields match between responses, we have higher confidence
                        for field in expected_fields:
                            if field in data2 and data2[field] == data[field]:
                                logger.info(f"LLM VALIDATION: Field '{field}' confirmed with value '{data[field]}'")
                            elif field in data2 and data2[field] is not None and data[field] is None:
                                # Second response found a value the first didn't
                                data[field] = data2[field]
                                logger.info(f"LLM VALIDATION: Updated field '{field}' with value '{data[field]}' from second response")
                    except:
                        pass
                                
                # Convert hospitalId to hospital_id for compatibility with existing code
                if 'hospitalId' in data and data['hospitalId'] is not None:
                    # Ensure hospitalId is an integer
                    try:
                        data['hospital_id'] = int(data['hospitalId'])
                    except (ValueError, TypeError):
                        # Try to extract just the digits if there's any text
                        if isinstance(data['hospitalId'], str):
                            import re
                            digits = re.findall(r'\d+', data['hospitalId'])
                            if digits:
                                data['hospital_id'] = int(digits[0])
                            else:
                                data['hospital_id'] = None
                        else:
                            data['hospital_id'] = None
                    del data['hospitalId']
                else:
                    data['hospital_id'] = None
                
                # Add default values for fields not collected via call
                data['latitude'] = 0.0
                data['longitude'] = 0.0
                data['alert'] = []
                
                return data
            except json.JSONDecodeError:
                logger.error(f"Error parsing LLM response as JSON: {response1}")
                # Attempt to extract structured data from non-JSON response
                try:
                    data = {}
                    if "patient" in response1.lower():
                        import re
                        patient_match = re.search(r'patient["\s:]+([^",\n]+)', response1)
                        if patient_match:
                            data['patient'] = patient_match.group(1).strip()
                    
                    if "hospital" in response1.lower():
                        hospital_match = re.search(r'hospital[_\s]*id["\s:]+(\d+)', response1)
                        if hospital_match:
                            data['hospital_id'] = int(hospital_match.group(1))
                    
                    # Add default values
                    data['latitude'] = 0.0
                    data['longitude'] = 0.0
                    data['alert'] = []
                    
                    if data:
                        logger.info(f"Extracted partial data from non-JSON response: {data}")
                        return data
                    return {}
                except:
                    return {}
        except Exception as e:
            logger.error(f"Error extracting appointment data: {e}")
            return {}
    
    def generate_follow_up_question(self, appointment_data):
        """
        Generate a follow-up question based on missing appointment data
        """
        system_prompt = """
        You are an AI assistant for a healthcare appointment booking system.
        Generate a natural, conversational follow-up question to gather missing information.
        Your response should be friendly and direct, asking for specific missing information.
        Focus ONLY on these fields: patient name, symptoms, date, time, or hospitalId.
        For hospitalId, ask directly for the numerical ID, not the hospital name.
        """
        
        try:
            # Determine what information is missing
            missing_fields = []
            if not appointment_data.get('patient'):
                missing_fields.append("your full name")
            if not appointment_data.get('hospital_id'):
                missing_fields.append("numerical hospital ID")
            if not appointment_data.get('date'):
                missing_fields.append("date for the appointment")
            if not appointment_data.get('time'):
                missing_fields.append("time for the appointment")
            if not appointment_data.get('symptoms'):
                missing_fields.append("symptoms or reason for the appointment")
            
            # Create a message for the LLM
            messages = [
                {
                    "role": "user", 
                    "content": f"I need to generate a follow-up question for a patient booking an appointment. Here's what I know so far: {json.dumps(appointment_data)}. The missing information is: {', '.join(missing_fields)}."
                }
            ]
            
            response = self._call_llm(messages, system_prompt)
            
            if response:
                return response
            else:
                # Fallback response
                if missing_fields:
                    return f"Could you please tell me {missing_fields[0]} for your appointment?"
                else:
                    return "Could you please provide more details about your appointment request?"
        except Exception as e:
            logger.error(f"Error generating follow-up question: {e}")
            return "Could you please provide more details about your appointment?"
    
    def verify_appointment_details(self, appointment_data, hospital_name):
        """
        Generate a confirmation message with all appointment details
        """
        system_prompt = """
        You are an AI assistant for a healthcare appointment booking system.
        Generate a detailed confirmation message that summarizes all appointment details.
        Confirm the patient's name, symptoms, date, time, and hospital name.
        Be conversational but clear, and ask for confirmation from the patient.
        """
        
        try:
            # Create a message for the LLM
            appointment_data["hospital_name"] = hospital_name
            
            messages = [
                {
                    "role": "user", 
                    "content": f"I need to generate a confirmation message for a patient booking an appointment. Here are the appointment details: {json.dumps(appointment_data)}."
                }
            ]
            
            response = self._call_llm(messages, system_prompt)
            
            if response:
                return response
            else:
                # Fallback response
                return f"I'd like to confirm your appointment for {appointment_data.get('patient', 'you')} at {hospital_name} on {appointment_data.get('date', 'the specified date')} at {appointment_data.get('time', 'the specified time')} for {appointment_data.get('symptoms', 'your health concern')}. Is this correct?"
        except Exception as e:
            logger.error(f"Error verifying appointment details: {e}")
            return f"I have your appointment details and would like to confirm them. Is this correct?"
    
    def analyze_user_response(self, user_input):
        """
        Analyze the user's response to determine if it's a confirmation, correction, or cancellation
        """
        system_prompt = """
        You are an AI assistant for a healthcare appointment booking system.
        Analyze the user's response to determine if they are confirming, correcting, or canceling.
        Respond with a JSON object that includes a 'response_type' field with one of these values:
        - 'confirm' if the user is confirming the appointment
        - 'correct' if the user wants to make corrections
        - 'cancel' if the user wants to cancel
        - 'unclear' if the user's intent is unclear
        """
        
        try:
            # Create a message for the LLM
            messages = [
                {"role": "user", "content": f"Analyze this response to an appointment confirmation: '{user_input}'"}
            ]
            
            response = self._call_llm(messages, system_prompt)
            
            if response:
                # Parse the JSON response
                try:
                    data = json.loads(response)
                    return data
                except json.JSONDecodeError:
                    logger.error(f"Error parsing LLM response as JSON: {response}")
                    return {"response_type": "unclear"}
            else:
                return {"response_type": "unclear"}
        except Exception as e:
            logger.error(f"Error analyzing user response: {e}")
            return {"response_type": "unclear"} 