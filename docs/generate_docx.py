from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

title = doc.add_heading('CourtLOG: System Overview & Production Guide', 0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

doc.add_heading('1. How the System Works', level=1)
p = doc.add_paragraph('CourtLOG is a full-stack, AI-augmented Case Management and Delay Compliance system designed specifically for the Judiciary. It bridges the gap between physical court operations (like bailiffs serving writs) and digital tracking.\n')
p.add_run('\n• The Backend (Python/FastAPI): ').bold = True
p.add_run('Acts as the brain of the system. It manages the database of cases, handles API requests from the frontend, and runs a background chron-job (Compliance Sweep) that checks for overdue cases. It integrates with WhatsApp to send automated alerts when cases breach their adjournment thresholds.')
p.add_run('\n• The Frontend (HTML/JS/Tailwind): ').bold = True
p.add_run('A premium, glassmorphic dashboard where judges, clerks, and the Deputy Chief Registrar (DCR) can log into their respective portals. It provides real-time analytics, QR chain-of-custody tracking, and visual badges for case status.')
p.add_run('\n• The AI/ML Layer: ').bold = True
p.add_run('CourtLOG utilizes a trained Random Forest classifier to predict the likelihood of case delays based on historical data.')

doc.add_heading('2. Security Features', level=1)
p2 = doc.add_paragraph('As a system handling sensitive judicial data, CourtLOG implements several layers of security:\n')
p2.add_run('\n• Role-Based Access Control (RBAC): ').bold = True
p2.add_run('Users log in with specific roles (Sheriff, Clerk, DCR, Judge). A Clerk cannot approve an override; only the DCR has the cryptographic/system authority to unblock overdue cases.')
p2.add_run('\n• Audit Logging (Chain of Custody): ').bold = True
p2.add_run('Every time a writ is moved, served, or adjourned, the system logs the exact timestamp and the ID of the personnel responsible. This prevents tampering and ensures accountability.')
p2.add_run('\n• Environment Variables: ').bold = True
p2.add_run('Sensitive information (like the WhatsApp API token and database credentials) is never hardcoded. It is loaded securely via a .env file.')

doc.add_heading('3. Applications and Impact', level=1)
p3 = doc.add_paragraph()
p3.add_run('• Eliminating Bottlenecks: ').bold = True
p3.add_run('By automatically flagging cases that have been adjourned more than 3 times, the Chief Judge can immediately spot administrative bottlenecks.')
p3.add_run('\n• Automated Accountability: ').bold = True
p3.add_run('Sheriffs receive automated WhatsApp messages the moment a writ becomes overdue, eliminating the "I forgot" or "I wasn\'t informed" excuses.')
p3.add_run('\n• Transparency for the NJC: ').bold = True
p3.add_run('The system includes a 1-click "Export NJC Report" feature, allowing courts to instantly generate compliance reports for the National Judicial Council, saving weeks of manual data entry.')

doc.add_heading('4. WhatsApp Business API: Step-by-Step Setup', level=1)
p4 = doc.add_paragraph('To move the WhatsApp messaging from the development/testing phase into production, you need a permanent WhatsApp API key from Meta (Facebook).')

doc.add_heading('Step 1: Create a Meta Developer App', level=2)
doc.add_paragraph('1. Go to developers.facebook.com and log in with your Meta/Facebook account.\n2. Click on My Apps (top right) and then click the green Create App button.\n3. Select Other (or Business) as the use case and hit Next.\n4. Select Business as the app type.\n5. Name your app (e.g., CourtLOG System) and connect it to your Facebook Business Manager account.')

doc.add_heading('Step 2: Add WhatsApp to Your App', level=2)
doc.add_paragraph('1. Once your app is created, you will be on the App Dashboard.\n2. Scroll down to find the WhatsApp product card and click Set Up.\n3. Meta will provide you with a temporary access token and a test phone number. Note: Temporary tokens expire every 24 hours.')

doc.add_heading('Step 3: Generate a Permanent System User Token', level=2)
doc.add_paragraph('To get a key that never expires for the .env file:\n1. Go to business.facebook.com and navigate to Business Settings.\n2. On the left sidebar, go to Users > System Users.\n3. Click Add to create a new System User (name it CourtLOG API User) and give it Admin access.\n4. Click on the new System User and select Generate New Token.\n5. Select your App from the dropdown.\n6. Check the permissions: whatsapp_business_messaging and whatsapp_business_management.\n7. Click Generate Token. Copy this extremely long string immediately.')

doc.add_heading('Step 4: Configure the .env File', level=2)
doc.add_paragraph('In your backend folder, create a new file named .env and add your credentials like this:\n\nWHATSAPP_TOKEN="PASTE_YOUR_LONG_PERMANENT_TOKEN_HERE"\nWHATSAPP_PHONE_ID="PASTE_YOUR_WHATSAPP_PHONE_NUMBER_ID_HERE"\n\nOnce this is saved, the Python backend will automatically load these credentials using python-dotenv and send real messages to production numbers!')

doc.save('CourtLOG_Overview.docx')
print("Successfully generated CourtLOG_Overview.docx")
