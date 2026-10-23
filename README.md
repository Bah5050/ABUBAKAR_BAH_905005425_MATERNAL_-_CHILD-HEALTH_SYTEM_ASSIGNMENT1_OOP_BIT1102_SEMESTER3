READ ME
About the project
MCHC is a Python console application built with Object-Oriented Programming. It addresses a real health need: helping a Maternal and Child Health Clinic keep records of mothers and their children. It falls under the Health domain as a patient record system with vaccination tracking.
A mother is registered as either an Antenatal patient (baby not yet born) or a Postnatal patient (baby already born), and the system automatically assigns her a Patient ID (for example, MCH001). Health workers add visit notes and update each child’s immunization status. Staff members get their own ID (for example, HW001 or RC002) when they sign up.
Features
•	Registers a new patient using the mother’s name, the child’s name (postnatal only), phone number, address and password
•	Generates patient and staff IDs automatically
•	Offers three user roles (Patient, Receptionist and Health Worker), each with its own menu
•	Lets patients log in to see their own information, history and immunization status
•	Lets receptionists register patients, view all patients and search by ID or name
•	Lets health workers also add visit notes, view history and update immunizations
•	Adds default vaccines (BCG, Polio 1, Polio 2) for postnatal patients, and allows new vaccines and completion dates to be recorded
•	Protects staff sign-up with an institution PIN
•	Includes a “Forgot my ID” option that verifies the name, address and phone number
•	Validates input and gives clear messages, such as “Wrong password.” and “Attempts left: 2”
•	Locks an account after 3 failed login attempts
•	Prevents duplicate patients (same mother’s name and phone number)
•	Saves data to a local file and loads it again when the program starts
How it meets Digital Public Goods (DPG) standards
•	Open-source: The complete source code is public on GitHub, so anyone can read, run and improve it.
•	Inclusive and accessible: It uses simple numbered text menus and plain-language prompts. It works offline and needs only Python, with no special hardware. Every menu includes a “go back” or “log out” option, and every invalid input produces a helpful message.
•	Privacy-respecting: Passwords are never stored as plain text; only a SHA-256 hash is kept. Patients can see only their own record, and receptionists cannot access visit history or immunization details. Records stay in a local file (mchc_data.json) on the user’s own computer and are never transmitted anywhere. Because this file contains contact details and health notes, it is excluded from GitHub through .gitignore, so only the code is public and never real patient data.
•	Modular and reusable: The code is organized into separate classes (Person, Vaccination, Patient, Staff, MCHCSystem), and each one can be reused in other projects.
Security note
The institution PIN for staff sign-up is defined in the code as INSTITUTION_PIN. The value in this public repository is just an example. Any institution that uses the program must replace it with its own secret code before real use.
OOP concepts used
Concept	Where it is used
Classes, attributes and objects	Person, Vaccination, Patient, Staff and MCHCSystem
Data structure: list	self.patients and self.staff_members in MCHCSystem, and history and vaccinations in Patient
Tuples	The DEFAULT_VACCINES and DAYS_IN_MONTH constants, and split_date, which returns (day, month, year)
Instance methods	add_visit_note, check_password, get_status, mark_completed, display_full_record
Class methods	generate_patient_id, generate_staff_id, from_list
Static methods	hash_password, is_valid_phone, is_valid_date, default_vaccinations
Inheritance	Patient and Staff extend Person
Encapsulation	The private __password_hash attribute in Person
Project structure
•	mchc.py: Contains the entire program (all classes and the main menu)
•	mchc_data.json: Created automatically when the program runs; not uploaded to GitHub
How to run
1.	Install Python 3.8 or newer. No extra libraries are required.
2.	Download mchc.py into a folder.
3.	Open a terminal in that folder and run: python mchc.py
Example usage
Sample screenshots of the program running are shown in the Screenshots section that follows.
Author
•	Author’s name: Abubakar Bah
•	Student ID: 905005425
