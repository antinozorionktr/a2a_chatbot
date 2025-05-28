import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Optional
import time

# Configure page
st.set_page_config(
    page_title="Medical Appointment System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        color: #2E86AB;
        font-size: 2.5rem;
        margin-bottom: 2rem;
    }
    .agent-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #2E86AB;
    }
    .success-message {
        background-color: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }
    .error-message {
        background-color: #f8d7da;
        color: #721c24;
        padding: 1rem;
        border-radius: 5px;
        border: 1px solid #f5c6cb;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

class AgentClient:
    """Client to communicate with the simplified HTTP API agents"""
    
    def __init__(self):
        self.doctor_agent_url = "http://35.91.66.200:9998"
        self.booking_agent_url = "http://35.91.66.200:9999"
        self.session = requests.Session()
        self.session.timeout = 30
    
    def send_message_to_agent(self, agent_url: str, message: str) -> Dict:
        """Send message to agent using simplified HTTP API"""
        try:
            # Simple JSON payload - just send the message
            payload = {"message": message}
            
            # Send to the root endpoint
            response = self.session.post(
                agent_url + "/",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                json_response = response.json()
                
                # The response format from multi_agent.py is:
                # {"success": True, "data": result.data, "timestamp": datetime.now().isoformat()}
                if json_response.get("success", False):
                    return {"success": True, "data": json_response.get("data", "")}
                else:
                    return {"success": False, "error": json_response.get("error", "Unknown error")}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except requests.exceptions.ConnectionError:
            return {"success": False, "error": "Connection failed. Make sure the agent server is running."}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Request timed out."}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    def query_doctor_directory(self, message: str) -> Dict:
        """Query the Doctor Directory Agent"""
        return self.send_message_to_agent(self.doctor_agent_url, message)
    
    def query_booking_agent(self, message: str) -> Dict:
        """Query the Booking Agent"""
        return self.send_message_to_agent(self.booking_agent_url, message)
    
    def check_agent_status(self, agent_url: str) -> bool:
        """Check if agent is running"""
        try:
            response = self.session.get(f"{agent_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def test_agent_endpoints(self, agent_url: str) -> Dict:
        """Test different endpoints to see what's available"""
        endpoints_to_test = [
            "/health",
            "/"
        ]
        
        results = {}
        for endpoint in endpoints_to_test:
            try:
                if endpoint == "/":
                    # Test the main endpoint with simple payload
                    test_payload = {"message": "test connection"}
                    response = self.session.post(f"{agent_url}{endpoint}", json=test_payload, timeout=5)
                else:
                    response = self.session.get(f"{agent_url}{endpoint}", timeout=5)
                
                results[endpoint] = {
                    "status": response.status_code,
                    "available": response.status_code < 400
                }
            except Exception as e:
                results[endpoint] = {
                    "status": "error",
                    "available": False,
                    "error": str(e)
                }
        
        return results

def display_response(response: Dict, agent_name: str):
    """Display agent response in a formatted way"""
    if response["success"]:
        data = response.get("data", "")
        
        if data and str(data).strip():
            st.markdown(f"**{agent_name} Response:**")
            # Format the response nicely
            if "━━━" in str(data):
                # Already formatted response - display as text to preserve formatting
                st.text(data)
            else:
                # Simple response - can use markdown
                st.markdown(str(data))
        else:
            st.info(f"✅ {agent_name} processed the request successfully (no content returned)")
    else:
        st.error(f"❌ {agent_name} Error: {response['error']}")

def main():
    # Initialize session state
    if 'agent_client' not in st.session_state:
        st.session_state.agent_client = AgentClient()
    
    # Main header
    st.markdown('<h1 class="main-header">🏥 Medical Appointment System</h1>', unsafe_allow_html=True)
    
    # Sidebar for agent status
    st.sidebar.header("🔧 Agent Status")
    
    doctor_status = st.session_state.agent_client.check_agent_status(
        st.session_state.agent_client.doctor_agent_url
    )
    booking_status = st.session_state.agent_client.check_agent_status(
        st.session_state.agent_client.booking_agent_url
    )
    
    st.sidebar.markdown(f"**Doctor Directory Agent:** {'🟢 Online' if doctor_status else '🔴 Offline'}")
    st.sidebar.markdown(f"**Booking Agent:** {'🟢 Online' if booking_status else '🔴 Offline'}")
    
    # Debug section in sidebar
    if st.sidebar.button("🔍 Debug Endpoints"):
        st.sidebar.write("**Doctor Agent Endpoints:**")
        doctor_endpoints = st.session_state.agent_client.test_agent_endpoints(
            st.session_state.agent_client.doctor_agent_url
        )
        for endpoint, info in doctor_endpoints.items():
            status = "✅" if info["available"] else "❌"
            st.sidebar.write(f"{status} {endpoint}: {info['status']}")
        
        st.sidebar.write("**Booking Agent Endpoints:**")
        booking_endpoints = st.session_state.agent_client.test_agent_endpoints(
            st.session_state.agent_client.booking_agent_url
        )
        for endpoint, info in booking_endpoints.items():
            status = "✅" if info["available"] else "❌"
            st.sidebar.write(f"{status} {endpoint}: {info['status']}")
    
    if not (doctor_status or booking_status):
        st.error("⚠️ No agents are running! Please start the agent servers first.")
        st.markdown("""
        **To start the agents, run:**
        ```bash
        # Terminal 1: Start Doctor Directory Agent
        python multi_agent.py doctor
        
        # Terminal 2: Start Booking Agent  
        python multi_agent.py booking
        
        # Or run both together:
        python multi_agent.py both
        ```
        """)
        return
    
    # Main interface tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 Doctor Directory", "📅 Book Appointment", "📋 Manage Appointments", "💬 Chat Interface"])
    
    # Tab 1: Doctor Directory
    with tab1:
        st.header("🏥 Doctor Directory")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Find Doctors")
            
            # Specialty filter
            specialty_options = ["All Specialties", "Cardiology", "Dermatology", "Pediatrics", "Orthopedics"]
            selected_specialty = st.selectbox("Select Specialty:", specialty_options)
            
            if st.button("🔍 Search Doctors", key="search_doctors"):
                if doctor_status:
                    with st.spinner("Searching doctors..."):
                        if selected_specialty == "All Specialties":
                            query = "list doctors"
                        else:
                            query = f"find doctors {selected_specialty.lower()}"
                        
                        response = st.session_state.agent_client.query_doctor_directory(query)
                        display_response(response, "Doctor Directory Agent")
                else:
                    st.error("Doctor Directory Agent is offline!")
        
        with col2:
            st.subheader("Quick Actions")
            
            # Doctor availability check
            doctor_id = st.text_input("Doctor ID:", placeholder="e.g., dr001")
            if st.button("📅 Check Availability", key="check_availability"):
                if doctor_status and doctor_id:
                    with st.spinner("Checking availability..."):
                        query = f"slots for {doctor_id}"
                        response = st.session_state.agent_client.query_doctor_directory(query)
                        display_response(response, "Doctor Directory Agent")
                elif not doctor_id:
                    st.warning("Please enter a doctor ID")
                else:
                    st.error("Doctor Directory Agent is offline!")
    
    # Tab 2: Book Appointment
    with tab2:
        st.header("📅 Book New Appointment")
        
        with st.form("booking_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                patient_name = st.text_input("Patient Name:", placeholder="Enter patient name")
                patient_phone = st.text_input("Phone Number (Optional):", placeholder="+1234567890")
                
            with col2:
                specialty = st.selectbox(
                    "Preferred Specialty:",
                    ["Any", "Cardiology", "Dermatology", "Pediatrics", "Orthopedics"]
                )
                time_preference = st.selectbox(
                    "Preferred Time:",
                    ["Any Time", "Morning", "Afternoon", "Evening"]
                )
            
            submitted = st.form_submit_button("📝 Book Appointment")
            
            if submitted:
                if booking_status and patient_name:
                    with st.spinner("Booking appointment..."):
                        # Construct booking query in natural language
                        query = f"book appointment for {patient_name}"
                        if specialty != "Any":
                            query += f" with {specialty} specialist"
                        if time_preference != "Any Time":
                            query += f" in the {time_preference.lower()}"
                        if patient_phone:
                            query += f" phone {patient_phone}"
                        
                        response = st.session_state.agent_client.query_booking_agent(query)
                        display_response(response, "Booking Agent")
                elif not patient_name:
                    st.warning("Please enter patient name")
                else:
                    st.error("Booking Agent is offline!")
    
    # Tab 3: Manage Appointments
    with tab3:
        st.header("📋 Appointment Management")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("View Appointments")
            
            view_patient_name = st.text_input("Patient Name (optional):", placeholder="Filter by patient name")
            
            if st.button("📋 List Appointments", key="list_appointments"):
                if booking_status:
                    with st.spinner("Fetching appointments..."):
                        if view_patient_name:
                            query = f"list appointments for {view_patient_name}"
                        else:
                            query = "list all appointments"
                        
                        response = st.session_state.agent_client.query_booking_agent(query)
                        display_response(response, "Booking Agent")
                else:
                    st.error("Booking Agent is offline!")
        
        with col2:
            st.subheader("Cancel Appointment")
            
            appointment_id = st.text_input("Appointment ID:", placeholder="e.g., APT0001")
            
            if st.button("❌ Cancel Appointment", key="cancel_appointment"):
                if booking_status and appointment_id:
                    with st.spinner("Cancelling appointment..."):
                        query = f"cancel appointment {appointment_id}"
                        response = st.session_state.agent_client.query_booking_agent(query)
                        display_response(response, "Booking Agent")
                elif not appointment_id:
                    st.warning("Please enter appointment ID")
                else:
                    st.error("Booking Agent is offline!")
    
    # Tab 4: Chat Interface
    with tab4:
        st.header("💬 Chat with Agents")
        
        # Initialize chat history
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        
        # Agent selection
        agent_choice = st.radio(
            "Select Agent:",
            ["Doctor Directory Agent", "Booking Agent"],
            horizontal=True
        )
        
        # Example queries
        st.markdown("**Example queries:**")
        if agent_choice == "Doctor Directory Agent":
            examples = [
                "list all doctors",
                "find cardiologists", 
                "show slots for dr001",
                "what doctors are available?"
            ]
        else:
            examples = [
                "book appointment for John Smith with cardiologist",
                "list appointments for Sarah",
                "cancel appointment APT0001",
                "show all scheduled appointments"
            ]
        
        cols = st.columns(len(examples))
        for i, example in enumerate(examples):
            if cols[i].button(f"📝 {example}", key=f"example_{i}"):
                st.session_state.example_query = example
        
        # Chat input
        user_input = st.text_input(
            "Enter your message:", 
            placeholder="Type your question or command...",
            value=st.session_state.get('example_query', ''),
            key="chat_input"
        )
        
        # Clear the example query after using it
        if 'example_query' in st.session_state:
            del st.session_state.example_query
        
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            send_button = st.button("📤 Send Message")
        
        with col2:
            clear_button = st.button("🗑️ Clear Chat")
        
        if send_button and user_input:
            # Add user message to chat history
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })
            
            # Send to appropriate agent
            if agent_choice == "Doctor Directory Agent" and doctor_status:
                response = st.session_state.agent_client.query_doctor_directory(user_input)
            elif agent_choice == "Booking Agent" and booking_status:
                response = st.session_state.agent_client.query_booking_agent(user_input)
            else:
                response = {"success": False, "error": f"{agent_choice} is offline"}
            
            # Add agent response to chat history
            if response["success"]:
                content = str(response.get("data", "Response processed successfully"))
                
                st.session_state.chat_history.append({
                    "role": "agent",
                    "content": content,
                    "agent": agent_choice,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
            else:
                st.session_state.chat_history.append({
                    "role": "error",
                    "content": response["error"],
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
            
            # Clear input and rerun to show updated chat
            st.rerun()
        
        if clear_button:
            st.session_state.chat_history = []
            st.rerun()
        
        # Display chat history
        if st.session_state.chat_history:
            st.markdown("### Chat History")
            for i, message in enumerate(reversed(st.session_state.chat_history[-10:])):  # Show last 10 messages
                if message["role"] == "user":
                    st.markdown(f"**You ({message['timestamp']}):** {message['content']}")
                elif message["role"] == "agent":
                    st.markdown(f"**{message['agent']} ({message['timestamp']}):**")
                    if "━━━" in message['content']:
                        st.text(message['content'])
                    else:
                        st.markdown(message['content'])
                else:  # error
                    st.error(f"**Error ({message['timestamp']}):** {message['content']}")
                st.markdown("---")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; margin-top: 2rem;'>
        <p>🏥 Medical Appointment System | Built with Streamlit & PydanticAI</p>
        <p><strong>Usage Tips:</strong></p>
        <ul style='text-align: left; max-width: 600px; margin: 0 auto;'>
            <li>Start with the Doctor Directory to find available doctors</li>
            <li>Use the Booking tab for quick appointment scheduling</li>
            <li>Check appointment status in the Management tab</li>
            <li>Use the Chat interface for natural language queries</li>
            <li>Try the example queries for common tasks</li>
            <li>Click "Debug Endpoints" in sidebar if you encounter connection issues</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()