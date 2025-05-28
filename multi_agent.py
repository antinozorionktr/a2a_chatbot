import asyncio
import json
import re
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union
import uvicorn
from dataclasses import dataclass, asdict
from enum import Enum

from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from starlette.responses import JSONResponse
from starlette.routing import Route

load_dotenv()

# Environment setup for OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    print("⚠️  Warning: OPENAI_API_KEY not found in environment variables")

# ===== SHARED DATA MODELS =====

class AppointmentStatus(Enum):
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"

@dataclass
class Doctor:
    id: str
    name: str
    specialty: str
    available_slots: List[str]
    consultation_fee: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class Appointment:
    id: str
    doctor_id: str
    doctor_name: str
    patient_name: str
    patient_phone: Optional[str]
    appointment_time: str
    specialty: str
    status: AppointmentStatus = AppointmentStatus.SCHEDULED
    consultation_fee: float = 0.0
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result['status'] = self.status.value
        return result

# ===== PYDANTIC MODELS FOR A2A =====

class DoctorSearchRequest(BaseModel):
    specialty: Optional[str] = None
    preferred_time: Optional[str] = None

class BookingRequest(BaseModel):
    patient_name: str
    specialty: Optional[str] = None
    preferred_time: Optional[str] = None
    patient_phone: Optional[str] = None

class AppointmentQuery(BaseModel):
    patient_name: Optional[str] = None
    appointment_id: Optional[str] = None

# ===== ENHANCED PARSING UTILITIES =====

class MessageParser:
    """Enhanced message parsing with better natural language understanding."""
    
    @staticmethod
    def extract_specialty(message: str) -> Optional[str]:
        """Extract medical specialty from message."""
        specialties = {
            'cardiology': ['cardiology', 'cardiologist', 'heart', 'cardiac'],
            'dermatology': ['dermatology', 'dermatologist', 'skin'],
            'pediatrics': ['pediatrics', 'pediatrician', 'child', 'children', 'kids'],
            'orthopedics': ['orthopedics', 'orthopedic', 'bone', 'joint'],
            'neurology': ['neurology', 'neurologist', 'brain', 'nerve']
        }
        
        message_lower = message.lower()
        for specialty, keywords in specialties.items():
            if any(keyword in message_lower for keyword in keywords):
                return specialty
        return None
    
    @staticmethod
    def extract_patient_name(message: str) -> Optional[str]:
        """Extract patient name from booking request."""
        patterns = [
            r'(?:for|patient)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            r'appointment\s+for\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
            r'book\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).title()
        return None
    
    @staticmethod
    def extract_time_preference(message: str) -> Optional[str]:
        """Extract time preference from message."""
        time_patterns = {
            'morning': ['morning', '9:00', '10:00', '11:00'],
            'afternoon': ['afternoon', '14:00', '15:00', '16:00'],
            'evening': ['evening', '17:00', '18:00']
        }
        
        message_lower = message.lower()
        for time_pref, keywords in time_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                return time_pref
        return None
    
    @staticmethod
    def extract_doctor_id(message: str) -> Optional[str]:
        """Extract doctor ID from message."""
        match = re.search(r'(dr\d+)', message.lower())
        return match.group(1) if match else None
    
    @staticmethod
    def extract_appointment_slot(message: str) -> Optional[str]:
        """Extract specific appointment slot from message."""
        pattern = r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})'
        match = re.search(pattern, message)
        return match.group(1) if match else None

# ===== GLOBAL DATA STORAGE =====

class GlobalDataStore:
    """Shared data store for both agents."""
    
    def __init__(self):
        self.doctors = [
            Doctor(
                id="dr001",
                name="Dr. Sarah Johnson",
                specialty="Cardiology",
                available_slots=["2025-05-29 09:00", "2025-05-29 14:00", "2025-05-30 10:00"],
                consultation_fee=150.0
            ),
            Doctor(
                id="dr002", 
                name="Dr. Michael Chen",
                specialty="Dermatology",
                available_slots=["2025-05-29 11:00", "2025-05-29 15:30", "2025-05-30 09:30"],
                consultation_fee=120.0
            ),
            Doctor(
                id="dr003",
                name="Dr. Emily Rodriguez",
                specialty="Pediatrics", 
                available_slots=["2025-05-29 13:00", "2025-05-30 11:00", "2025-05-30 16:00"],
                consultation_fee=100.0
            ),
            Doctor(
                id="dr004",
                name="Dr. James Wilson",
                specialty="Orthopedics",
                available_slots=["2025-05-29 10:00", "2025-05-30 14:00", "2025-05-31 09:00"],
                consultation_fee=180.0
            )
        ]
        self.appointments: List[Appointment] = []
        self.appointment_counter = 1

# Global shared data store
data_store = GlobalDataStore()

# ===== DOCTOR DIRECTORY AGENT (PydanticAI) =====

def create_doctor_directory_agent():
    """Create PydanticAI Doctor Directory Agent."""
    
    instructions = """
    You are a Doctor Directory Agent that manages comprehensive doctor information and availability.
    
    Your capabilities include:
    - Listing available doctors by specialty
    - Showing doctor availability and time slots  
    - Reserving appointment slots
    - Providing detailed doctor information including fees
    
    Available doctors and their current slots are managed in the global data store.
    
    When users ask to:
    - "list doctors" or "find doctors" - show available doctors, optionally filtered by specialty
    - "slots for [doctor_id]" - show availability for specific doctor
    - "reserve [doctor_id] [time]" - reserve a time slot
    
    Always provide helpful, formatted responses with clear information about doctors, specialties, and availability.
    """
    
    doctor_agent = Agent(
        'openai:gpt-4o-mini',  # Using a more cost-effective model
        instructions=instructions,
        name='Doctor Directory Agent'
    )
    
    @doctor_agent.tool
    async def list_doctors(context: RunContext, specialty: Optional[str] = None) -> str:
        """List available doctors, optionally filtered by specialty."""
        try:
            filtered_doctors = data_store.doctors
            if specialty:
                filtered_doctors = [
                    d for d in data_store.doctors 
                    if specialty.lower() in d.specialty.lower()
                ]
            
            if not filtered_doctors:
                return f"No doctors found for {specialty or 'any specialty'}"
            
            response = f"Available doctors{' for ' + specialty if specialty else ''}:\n"
            for doc in filtered_doctors:
                slots_text = ', '.join(doc.available_slots) if doc.available_slots else 'No slots available'
                response += f"• {doc.name} (ID: {doc.id}, {doc.specialty}) - Fee: ${doc.consultation_fee}\n"
                response += f"  Available: {slots_text}\n"
            
            return response
        except Exception as e:
            return f"Error listing doctors: {str(e)}"
    
    @doctor_agent.tool
    async def get_doctor_slots(context: RunContext, doctor_id: str) -> str:
        """Get available slots for a specific doctor."""
        try:
            for doctor in data_store.doctors:
                if doctor.id == doctor_id:
                    if doctor.available_slots:
                        response = f"Available slots for {doctor.name}:\n"
                        response += f"Specialty: {doctor.specialty}\n"
                        response += f"Consultation Fee: ${doctor.consultation_fee}\n"
                        response += f"Slots: {', '.join(doctor.available_slots)}"
                        return response
                    else:
                        return f"No available slots for {doctor.name}"
            return f"Doctor {doctor_id} not found"
        except Exception as e:
            return f"Error getting slots: {str(e)}"
    
    @doctor_agent.tool
    async def reserve_slot(context: RunContext, doctor_id: str, slot: str) -> str:
        """Reserve a time slot for a doctor."""
        try:
            for doctor in data_store.doctors:
                if doctor.id == doctor_id and slot in doctor.available_slots:
                    doctor.available_slots.remove(slot)
                    response = f"✅ Slot reserved successfully!\n"
                    response += f"Doctor: {doctor.name} ({doctor.specialty})\n"
                    response += f"Time: {slot}\n"
                    response += f"Fee: ${doctor.consultation_fee}"
                    return response
            return "❌ Slot not available or doctor not found"
        except Exception as e:
            return f"Error reserving slot: {str(e)}"
    
    return doctor_agent

# ===== BOOKING AGENT (PydanticAI) =====

def create_booking_agent():
    """Create PydanticAI Booking Agent."""
    
    instructions = """
    You are a Medical Appointment Booking Agent that handles appointment scheduling and management.
    
    Your capabilities include:
    - Booking new appointments for patients
    - Listing existing appointments
    - Cancelling appointments
    - Managing appointment details including patient information
    
    When booking appointments:
    - Extract patient name, specialty preference, and time preference from requests
    - Find suitable doctors and available slots
    - Create appointment records with unique IDs
    - Provide confirmation details
    
    When listing appointments:
    - Show all appointments or filter by patient name
    - Display comprehensive appointment information
    
    When cancelling:
    - Find appointment by ID and update status
    - Release the time slot back to the doctor's availability
    
    Always provide clear, formatted responses with appointment details.
    """
    
    booking_agent = Agent(
        'openai:gpt-4o-mini',  # Using a more cost-effective model
        instructions=instructions,
        name='Medical Booking Agent'
    )
    
    @booking_agent.tool
    async def book_appointment(
        context: RunContext,
        patient_name: str, 
        specialty: Optional[str] = None, 
        preferred_time: Optional[str] = None,
        patient_phone: Optional[str] = None
    ) -> str:
        """Book an appointment for a patient."""
        try:
            # Get available doctors
            doctors = data_store.doctors
            if specialty:
                doctors = [d for d in doctors if specialty.lower() in d.specialty.lower()]
            
            if not doctors:
                return f"❌ No doctors available for {specialty or 'any specialty'}"
            
            # Find a suitable doctor and time slot
            for doctor in doctors:
                if not doctor.available_slots:
                    continue
                
                selected_slot = None
                
                # If preferred time specified, try to find matching slot
                if preferred_time:
                    time_patterns = {
                        'morning': ['09:00', '10:00', '11:00'],
                        'afternoon': ['14:00', '15:00', '16:00'],
                        'evening': ['17:00', '18:00']
                    }
                    
                    if preferred_time in time_patterns:
                        for slot in doctor.available_slots:
                            if any(time in slot for time in time_patterns[preferred_time]):
                                selected_slot = slot
                                break
                    else:
                        # Look for exact time match
                        for slot in doctor.available_slots:
                            if preferred_time in slot:
                                selected_slot = slot
                                break
                
                # Otherwise, take the first available slot
                if not selected_slot and doctor.available_slots:
                    selected_slot = doctor.available_slots[0]
                
                if selected_slot:
                    # Reserve the slot
                    doctor.available_slots.remove(selected_slot)
                    
                    # Create appointment
                    appointment = Appointment(
                        id=f"APT{data_store.appointment_counter:04d}",
                        doctor_id=doctor.id,
                        doctor_name=doctor.name,
                        patient_name=patient_name,
                        patient_phone=patient_phone,
                        appointment_time=selected_slot,
                        specialty=doctor.specialty,
                        consultation_fee=doctor.consultation_fee
                    )
                    data_store.appointments.append(appointment)
                    data_store.appointment_counter += 1
                    
                    return f"""✅ Appointment booked successfully!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Appointment ID: {appointment.id}
👤 Patient: {patient_name}
👨‍⚕️ Doctor: {doctor.name} ({doctor.specialty})
🕐 Time: {selected_slot}
💰 Consultation Fee: ${doctor.consultation_fee}
📞 Contact: {patient_phone or 'Not provided'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Please arrive 15 minutes early."""
            
            return "❌ No available appointments found matching your criteria"
            
        except Exception as e:
            return f"❌ Booking failed: {str(e)}"
    
    @booking_agent.tool
    async def list_appointments(context: RunContext, patient_name: Optional[str] = None) -> str:
        """List appointments, optionally filtered by patient name."""
        try:
            if not data_store.appointments:
                return "📅 No appointments scheduled"
            
            filtered_appointments = data_store.appointments
            
            if patient_name:
                filtered_appointments = [
                    apt for apt in filtered_appointments 
                    if patient_name.lower() in apt.patient_name.lower()
                ]
            
            if not filtered_appointments:
                filter_desc = f" for {patient_name}" if patient_name else ""
                return f"📅 No appointments found{filter_desc}"
            
            result = "📅 Scheduled Appointments:\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            for apt in filtered_appointments:
                status_emoji = {
                    AppointmentStatus.SCHEDULED: "🗓️",
                    AppointmentStatus.CONFIRMED: "✅",
                    AppointmentStatus.CANCELLED: "❌",
                    AppointmentStatus.COMPLETED: "✔️"
                }
                result += f"{status_emoji.get(apt.status, '📋')} {apt.id} | {apt.patient_name}\n"
                result += f"   👨‍⚕️ {apt.doctor_name} ({apt.specialty})\n"
                result += f"   🕐 {apt.appointment_time} | 💰 ${apt.consultation_fee}\n"
                result += f"   📊 Status: {apt.status.value.title()}\n"
                if apt.patient_phone:
                    result += f"   📞 {apt.patient_phone}\n"
                result += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            
            return result
        except Exception as e:
            return f"Error listing appointments: {str(e)}"
    
    @booking_agent.tool
    async def cancel_appointment(context: RunContext, appointment_id: str) -> str:
        """Cancel an appointment and release the slot."""
        try:
            for appointment in data_store.appointments:
                if appointment.id == appointment_id:
                    if appointment.status == AppointmentStatus.CANCELLED:
                        return f"❌ Appointment {appointment_id} is already cancelled"
                    
                    # Release the slot back to the doctor
                    for doctor in data_store.doctors:
                        if doctor.id == appointment.doctor_id:
                            doctor.available_slots.append(appointment.appointment_time)
                            doctor.available_slots.sort()
                            break
                    
                    appointment.status = AppointmentStatus.CANCELLED
                    return f"✅ Appointment {appointment_id} has been cancelled successfully"
            
            return f"❌ Appointment {appointment_id} not found"
        except Exception as e:
            return f"Error cancelling appointment: {str(e)}"
    
    return booking_agent

# ===== ENHANCED MESSAGE PROCESSING =====

async def process_user_message(agent, message: str) -> str:
    """Process user message with enhanced parsing and agent routing."""
    try:
        message_lower = message.lower()
        
        # Enhanced parsing for better natural language understanding
        specialty = MessageParser.extract_specialty(message)
        patient_name = MessageParser.extract_patient_name(message)
        time_preference = MessageParser.extract_time_preference(message)
        doctor_id = MessageParser.extract_doctor_id(message)
        appointment_slot = MessageParser.extract_appointment_slot(message)
        
        # Extract phone number if provided
        phone_match = re.search(r'(\+?\d[\d\s\-\(\)]{8,}\d)', message)
        patient_phone = phone_match.group(1) if phone_match else None
        
        # Extract appointment ID
        apt_id_match = re.search(r'(APT\d{4})', message.upper())
        appointment_id = apt_id_match.group(1) if apt_id_match else None
        
        # Process message with parsed context
        if agent.name == 'Doctor Directory Agent':
            if any(cmd in message_lower for cmd in ["list doctors", "show doctors", "find doctors"]):
                context = f"List doctors for specialty: {specialty}" if specialty else "List all doctors"
            elif "slots for" in message_lower or "availability for" in message_lower:
                context = f"Show slots for doctor {doctor_id}" if doctor_id else "Show doctor availability"
            elif "reserve" in message_lower:
                context = f"Reserve slot {appointment_slot} for doctor {doctor_id}" if doctor_id and appointment_slot else "Reserve appointment slot"
            else:
                context = "General doctor directory inquiry"
        else:  # Booking Agent
            if any(cmd in message_lower for cmd in ["book appointment", "schedule appointment", "make appointment"]):
                context = f"Book appointment for {patient_name or 'patient'}"
                if specialty:
                    context += f" in {specialty}"
                if time_preference:
                    context += f" at {time_preference}"
            elif any(cmd in message_lower for cmd in ["list appointments", "show appointments", "my appointments"]):
                context = f"List appointments for {patient_name}" if patient_name else "List all appointments"
            elif "cancel appointment" in message_lower:
                context = f"Cancel appointment {appointment_id}" if appointment_id else "Cancel appointment"
            else:
                context = "General booking inquiry"
        
        # Run the agent with enhanced context
        full_message = f"{context}\n\nUser message: {message}"
        result = await agent.run(full_message)
        return result.data
        
    except Exception as e:
        return f"❌ Error processing message: {str(e)}"

# ===== SIMPLE HTTP SERVER (instead of A2A) =====

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import json

def create_doctor_directory_server():
    """Create Doctor Directory HTTP server with simple API."""
    agent = create_doctor_directory_agent()
    
    async def handle_message(request: Request):
        try:
            body = await request.body()
            data = json.loads(body)
            
            # Handle both simple text and JSON-RPC format
            if isinstance(data, dict):
                if "data" in data:
                    message = data["data"]
                elif "params" in data and "data" in data["params"]:
                    message = data["params"]["data"]
                elif "message" in data:
                    message = data["message"]
                else:
                    message = str(data)
            else:
                message = str(data)
            
            # Process the message with the agent
            result = await agent.run(message)
            
            # Return result in consistent format
            return JSONResponse({
                "success": True,
                "data": result.data,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, status_code=500)
    
    async def health_check(request: Request):
        return JSONResponse({
            "status": "ok", 
            "agent": "Doctor Directory Agent",
            "timestamp": datetime.now().isoformat()
        })
    
    routes = [
        Route('/', handle_message, methods=['POST']),
        Route('/health', health_check, methods=['GET']),
    ]
    
    app = Starlette(routes=routes)
    return app

def create_booking_server():
    """Create Booking HTTP server with simple API."""
    agent = create_booking_agent()
    
    async def handle_message(request: Request):
        try:
            body = await request.body()
            data = json.loads(body)
            
            # Handle both simple text and JSON-RPC format
            if isinstance(data, dict):
                if "data" in data:
                    message = data["data"]
                elif "params" in data and "data" in data["params"]:
                    message = data["params"]["data"]
                elif "message" in data:
                    message = data["message"]
                else:
                    message = str(data)
            else:
                message = str(data)
            
            # Process the message with the agent
            result = await agent.run(message)
            
            # Return result in consistent format
            return JSONResponse({
                "success": True,
                "data": result.data,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, status_code=500)
    
    async def health_check(request: Request):
        return JSONResponse({
            "status": "ok", 
            "agent": "Booking Agent",
            "timestamp": datetime.now().isoformat()
        })
    
    routes = [
        Route('/', handle_message, methods=['POST']),
        Route('/health', health_check, methods=['GET']),
    ]
    
    app = Starlette(routes=routes)
    return app

# ===== SERVER RUNNERS =====

def run_doctor_directory_agent():
    """Run only the Doctor Directory Agent."""
    if not OPENAI_API_KEY:
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        return
    
    app = create_doctor_directory_server()
    print("🏥 Starting Doctor Directory Agent on http://localhost:9998")
    print("   Health check: http://localhost:9998/health")
    uvicorn.run(app, host='0.0.0.0', port=9998)

def run_booking_agent():
    """Run only the Booking Agent."""
    if not OPENAI_API_KEY:
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        return
    
    app = create_booking_server()
    print("📅 Starting Medical Booking Agent on http://localhost:9999")
    print("   Health check: http://localhost:9999/health")
    uvicorn.run(app, host='0.0.0.0', port=9999)

async def run_both_agents():
    """Run both agents concurrently."""
    if not OPENAI_API_KEY:
        print("❌ Error: OPENAI_API_KEY environment variable is required")
        return
    
    async def start_doctor_server():
        app = create_doctor_directory_server()
        config = uvicorn.Config(app=app, host='0.0.0.0', port=9998, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    async def start_booking_server():
        app = create_booking_server()
        config = uvicorn.Config(app=app, host='0.0.0.0', port=9999, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    print("🏥 Starting both Medical Appointment agents...")
    print("   Doctor Directory: http://localhost:9998")
    print("   Booking Agent: http://localhost:9999")
    print("   Both agents use simplified HTTP API instead of A2A protocol")
    
    await asyncio.gather(
        start_doctor_server(),
        start_booking_server()
    )

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'doctor':
            run_doctor_directory_agent()
        elif sys.argv[1] == 'booking':
            run_booking_agent()
        elif sys.argv[1] == 'both':
            asyncio.run(run_both_agents())
        else:
            print("Usage: python multi_agent.py [doctor|booking|both]")
    else:
        print("🏥 Medical Appointment System with PydanticAI Agents")
        print("Choose which agent to run:")
        print("• python multi_agent.py doctor    # Run Doctor Directory Agent")
        print("• python multi_agent.py booking   # Run Medical Booking Agent") 
        print("• python multi_agent.py both      # Run both agents")
        print("\n⚠️  Make sure to set your OpenAI API key:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("\n📝 Note: Using simplified HTTP API instead of A2A protocol for compatibility")