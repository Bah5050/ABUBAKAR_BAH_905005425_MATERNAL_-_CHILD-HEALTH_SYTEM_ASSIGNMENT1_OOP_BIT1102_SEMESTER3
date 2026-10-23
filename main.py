
"""
Maternal and Child Health Clinic System (MCHC)
==============================================

"""

import contextlib
import getpass
import hashlib
import hmac
import json
import os
import re
import shutil
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Settings and constants
# ---------------------------------------------------------------------------
# IMPORTANT: this value is only an example. Any institution using this program will chnage or make their pin private #
INSTITUTION_PIN = "MCHC2026"

DATA_FILE = "mchc_data.json"
MAX_ATTEMPTS = 3
MIN_PASSWORD_LENGTH = 6

# Tuples: fixed values that never change while the program runs.
DEFAULT_VACCINES = ("BCG", "Polio 1", "Polio 2")
DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

ANTENATAL = "Antenatal"  # pregnant mother, baby not yet born
POSTNATAL = "Postnatal"  # baby has been born
HEALTH_WORKER = "Health Worker"
RECEPTIONIST = "Receptionist"


# ---------------------------------------------------------------------------
# Small helper functions
# ---------------------------------------------------------------------------
def split_date(text):
    """Split 'DD/MM/YYYY' into the tuple (day, month, year), or None."""
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", text)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def today_string():
    """Today's date as DD/MM/YYYY."""
    return datetime.now().astimezone().strftime("%d/%m/%Y")


def normalize_text(text):
    """Lower-case text and collapse extra spaces so names compare fairly."""
    return " ".join(text.lower().split())


def same_text(first, second):
    return normalize_text(first) == normalize_text(second)


def fit(text, width):
    """Cut or pad text so table columns line up."""
    if len(text) > width - 1:
        return (text[: width - 3] + "..").ljust(width)
    return text.ljust(width)


# ---------------------------------------------------------------------------
# Vaccination
# ---------------------------------------------------------------------------
class Vaccination:
    """One vaccine for a child, with its completion status."""

    def __init__(self, name, completed=False, date_completed=None):
        self.name = name
        self.completed = completed
        self.date_completed = date_completed

    # --- instance methods ---
    def get_status(self):
        if not self.completed:
            return "Due"
        if self.date_completed is None:
            return "Completed"
        return f"Completed ({self.date_completed})"

    def mark_completed(self, date_text):
        self.completed = True
        self.date_completed = date_text

    def to_dict(self):
        return {
            "name": self.name,
            "completed": self.completed,
            "date_completed": self.date_completed,
        }

    # --- class methods ---
    @classmethod
    def from_dict(cls, data):
        return cls(
            data["name"],
            bool(data.get("completed", False)),
            data.get("date_completed"),
        )

    @classmethod
    def from_list(cls, items):
        """Build a list of Vaccination objects from a list of dictionaries."""
        return [cls.from_dict(item) for item in items]

    # --- static methods ---
    @staticmethod
    def default_vaccinations():
        """A fresh list with the default vaccines, all marked Due."""
        return [Vaccination(name) for name in DEFAULT_VACCINES]

    @staticmethod
    def is_valid_date(text):
        """True for a real DD/MM/YYYY date that is not in the future."""
        parts = split_date(text)
        if parts is None:
            return False
        day, month, year = parts
        if year < 1900 or month < 1 or month > 12:
            return False

        max_day = DAYS_IN_MONTH[month - 1]
        is_leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        if month == 2 and is_leap:
            max_day = 29
        if day < 1 or day > max_day:
            return False

        now = datetime.now().astimezone()
        return datetime(year, month, day, tzinfo=now.tzinfo) <= now


# ---------------------------------------------------------------------------
# Person (base class)
# ---------------------------------------------------------------------------
class Person:
    """Base class for anyone who has an account: Patient and Staff extend it.

    The password hash is private (encapsulation): other code cannot read or
    change it directly and must use check_password().
    """

    def __init__(self, name, password=None, password_hash=None):
        self.name = name
        if password_hash is not None:
            self.__password_hash = password_hash
        elif password is not None:
            self.__password_hash = Person.hash_password(password)
        else:
            raise ValueError("A password or a password hash is required.")

    # --- instance methods ---
    def check_password(self, password):
        """True when the typed password matches the stored hash."""
        typed = Person.hash_password(password)
        return hmac.compare_digest(typed, self.__password_hash)

    def get_password_hash(self):
        """Only used when saving to the data file (never the real password)."""
        return self.__password_hash

    # --- static methods ---
    @staticmethod
    def hash_password(password):
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_phone(text):
        return re.sub(r"[\s\-]", "", text)

    @staticmethod
    def is_valid_phone(text):
        """8 to 15 digits, with an optional leading +."""
        cleaned = Person.normalize_phone(text)
        return re.match(r"^\+?\d{8,15}$", cleaned) is not None


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------
class Patient(Person):
    """A mother registered at the clinic (Antenatal or Postnatal)."""

    def __init__(
        self,
        patient_id,
        care_type,
        mother_name,
        child_name,
        phone,
        address,
        password=None,
        password_hash=None,
        last_visit="",
        history=None,
        vaccinations=None,
    ):
        super().__init__(mother_name, password, password_hash)
        self.patient_id = patient_id
        self.care_type = care_type
        self.child_name = child_name
        self.phone = phone
        self.address = address
        self.last_visit = last_visit
        self.history = history if history is not None else []
        self.vaccinations = vaccinations if vaccinations is not None else []

    @property
    def mother_name(self):
        return self.name

    # --- instance methods ---
    def is_antenatal(self):
        return self.care_type == ANTENATAL

    def last_visit_label(self):
        return self.last_visit or "No visit yet"

    def add_visit_note(self, note, staff_name):
        """Add a note to the history and update the last visit date."""
        date_text = today_string()
        self.history.append(f"{date_text} - {note} (by {staff_name})")
        self.last_visit = date_text
        return date_text

    def find_vaccination(self, name):
        for vaccine in self.vaccinations:
            if same_text(vaccine.name, name):
                return vaccine
        return None

    def add_vaccination(self, name):
        """Add a new vaccine as Due. Returns False if it is already listed."""
        if self.find_vaccination(name) is not None:
            return False
        self.vaccinations.append(Vaccination(name))
        return True

    def display_basic(self):
        print("\n===== PATIENT INFORMATION =====")
        print(f"Patient ID   : {self.patient_id}")
        print(f"Care Type    : {self.care_type}")
        print(f"Mother Name  : {self.name}")
        if not self.is_antenatal():
            print(f"Child Name   : {self.child_name}")
        print(f"Phone Number : {self.phone}")
        print(f"Address      : {self.address}")
        print(f"Last Visit   : {self.last_visit_label()}")

    def display_history(self):
        print("\n===== PATIENT HISTORY =====")
        if not self.history:
            print("No history recorded yet.")
            return
        for item in self.history:
            print(f"- {item}")

    def display_immunization(self):
        print("\n===== IMMUNIZATION STATUS =====")
        if self.is_antenatal():
            print(
                "Not applicable yet. Immunization starts after the baby is "
                "born (postnatal)."
            )
            return
        if not self.vaccinations:
            print("No vaccinations recorded yet.")
            return
        for vaccine in self.vaccinations:
            print(f"- {vaccine.name}: {vaccine.get_status()}")

    def display_full_record(self):
        self.display_basic()
        self.display_history()
        self.display_immunization()

    def to_dict(self):
        return {
            "patient_id": self.patient_id,
            "care_type": self.care_type,
            "mother_name": self.name,
            "child_name": self.child_name,
            "phone": self.phone,
            "address": self.address,
            "password_hash": self.get_password_hash(),
            "last_visit": self.last_visit,
            "history": list(self.history),
            "vaccinations": [v.to_dict() for v in self.vaccinations],
        }

    # --- class methods ---
    @classmethod
    def generate_patient_id(cls, counter):
        """Counter 1 gives MCH001, counter 12 gives MCH012, and so on."""
        return f"MCH{counter:03d}"

    @classmethod
    def from_dict(cls, data):
        return cls(
            patient_id=data["patient_id"],
            care_type=data["care_type"],
            mother_name=data["mother_name"],
            child_name=data.get("child_name", ""),
            phone=data["phone"],
            address=data.get("address", ""),
            password_hash=data["password_hash"],
            last_visit=data.get("last_visit", ""),
            history=list(data.get("history", [])),
            vaccinations=Vaccination.from_list(data.get("vaccinations", [])),
        )

    @classmethod
    def from_list(cls, items):
        """Build a list of Patient objects from a list of dictionaries."""
        return [cls.from_dict(item) for item in items]


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
class Staff(Person):
    """A Health Worker or a Receptionist."""

    def __init__(
        self, staff_id, name, role, password=None, password_hash=None
    ):
        super().__init__(name, password, password_hash)
        self.staff_id = staff_id
        self.role = role

    def to_dict(self):
        return {
            "staff_id": self.staff_id,
            "name": self.name,
            "role": self.role,
            "password_hash": self.get_password_hash(),
        }

    @classmethod
    def generate_staff_id(cls, role, counter):
        """HW001 for health workers, RC002 for receptionists, and so on."""
        prefix = "HW" if role == HEALTH_WORKER else "RC"
        return f"{prefix}{counter:03d}"

    @classmethod
    def from_dict(cls, data):
        return cls(
            staff_id=data["staff_id"],
            name=data["name"],
            role=data["role"],
            password_hash=data["password_hash"],
        )

    @classmethod
    def from_list(cls, items):
        """Build a list of Staff objects from a list of dictionaries."""
        return [cls.from_dict(item) for item in items]


# ---------------------------------------------------------------------------
# MCHCSystem (the clinic program)
# ---------------------------------------------------------------------------
class MCHCSystem:
    """Holds all patients and staff, handles saving, login and the menus."""

    def __init__(self, data_file=DATA_FILE):
        self.data_file = data_file
        self.patients = []  # list of Patient objects
        self.staff_members = []  # list of Staff objects
        self.patient_counter = 1
        self.staff_counter = 1

        # Login protection (lasts until the program is closed)
        self.failed_attempts = {}
        self.locked_keys = set()
        self.staff_signup_locked = False

        self.load_data()

    # ------------------------------------------------------------------
    # Saving and loading
    # ------------------------------------------------------------------
    def save_data(self):
        data = {
            "patient_counter": self.patient_counter,
            "staff_counter": self.staff_counter,
            "patients": [p.to_dict() for p in self.patients],
            "staff": [s.to_dict() for s in self.staff_members],
        }
        temp_file = self.data_file + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            os.replace(temp_file, self.data_file)
        except OSError as error:
            print(f"\nWarning: could not save data ({error}).")

    def load_data(self):
        if not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, encoding="utf-8") as handle:
                data = json.load(handle)
            self.patient_counter = int(data.get("patient_counter", 1))
            self.staff_counter = int(data.get("staff_counter", 1))
            self.patients = Patient.from_list(data.get("patients", []))
            self.staff_members = Staff.from_list(data.get("staff", []))
        except (ValueError, KeyError, TypeError, OSError):
            print(
                "\nWarning: saved data could not be read. A backup copy was "
                "kept and the system will start empty."
            )
            with contextlib.suppress(OSError):
                shutil.copy(self.data_file, self.data_file + ".bak")
            self.patients = []
            self.staff_members = []
            self.patient_counter = 1
            self.staff_counter = 1

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------
    def end_program(self):
        print("\nInput closed. Goodbye.")
        self.save_data()
        sys.exit(0)

    def ask(self, label):
        try:
            return input(label).strip()
        except EOFError:
            self.end_program()

    def ask_hidden(self, label):
        """Read a password or PIN without showing it on screen."""
        try:
            return getpass.getpass(label).strip()
        except EOFError:
            self.end_program()

    def ask_required(self, label):
        while True:
            value = self.ask(label)
            if value:
                return value
            print("This field cannot be empty.")

    @staticmethod
    def is_valid_name(text):
        if len(text) < 2 or len(text) > 60 or not text[0].isalpha():
            return False
        return all(ch.isalpha() or ch in " .'-" for ch in text)

    def ask_name(self, label):
        while True:
            value = self.ask(label)
            if self.is_valid_name(value):
                return value
            print(
                "Please enter a valid name (letters only, at least "
                "2 characters)."
            )

    def ask_address(self, label):
        while True:
            value = self.ask(label)
            if len(value) >= 3:
                return value
            print("Please enter a valid address (at least 3 characters).")

    def ask_phone(self, label):
        while True:
            value = self.ask(label)
            if Person.is_valid_phone(value):
                return Person.normalize_phone(value)
            print("Please enter a valid phone number (8 to 15 digits).")

    def ask_new_password(self):
        while True:
            password = self.ask_hidden(
                "Create a password (at least "
                f"{MIN_PASSWORD_LENGTH} characters): "
            )
            if len(password) < MIN_PASSWORD_LENGTH:
                print("The password is too short.")
                continue
            if self.ask_hidden("Confirm the password: ") != password:
                print("The passwords do not match. Please try again.")
                continue
            return password

    def ask_date_or_today(self, label):
        while True:
            value = self.ask(label)
            if not value:
                return today_string()
            if Vaccination.is_valid_date(value):
                return value
            print(
                "Please enter a valid date as DD/MM/YYYY, or press Enter "
                "for today."
            )

    def ask_care_type(self, allow_back=False):
        """Returns ANTENATAL or POSTNATAL (None if the person goes back)."""
        while True:
            print("\nIs the patient Antenatal or Postnatal?")
            print("1. Antenatal (pregnant, baby not yet born)")
            print("2. Postnatal (baby has been born)")
            if allow_back:
                print("3. Go back")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                return ANTENATAL
            if choice == "2":
                return POSTNATAL
            if allow_back and choice == "3":
                return None
            print("\nInvalid option!")

    def pause(self):
        self.ask("\nPress Enter to continue...")

    # ------------------------------------------------------------------
    # Login protection
    # ------------------------------------------------------------------
    def register_failure(self, key):
        """Count a failed attempt. Returns True if the account gets locked."""
        count = self.failed_attempts.get(key, 0) + 1
        self.failed_attempts[key] = count

        if count >= MAX_ATTEMPTS:
            self.locked_keys.add(key)
            print(
                "\nToo many failed attempts. This account is locked until "
                "the system is restarted."
            )
            return True

        print(f"Attempts left: {MAX_ATTEMPTS - count}")
        return False

    def clear_failures(self, key):
        self.failed_attempts.pop(key, None)

    # ------------------------------------------------------------------
    # Lookups (the list of objects is searched with simple loops)
    # ------------------------------------------------------------------
    def find_patient_by_id(self, patient_id):
        for patient in self.patients:
            if patient.patient_id.lower() == patient_id.lower():
                return patient
        return None

    def find_staff_by_id(self, staff_id, role):
        for staff in self.staff_members:
            if (
                staff.staff_id.lower() == staff_id.lower()
                and staff.role == role
            ):
                return staff
        return None

    def find_duplicate_patient(self, mother_name, phone):
        for patient in self.patients:
            if same_text(patient.name, mother_name) and patient.phone == phone:
                return patient
        return None

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------
    @staticmethod
    def print_id_card(title, identifier):
        print("\n+------------------------------------+")
        print(f"  {title}")
        print(f"  {identifier}")
        print("+------------------------------------+")

    @staticmethod
    def print_patient_table(patient_list):
        if not patient_list:
            print("\nNo patients registered yet.")
            return

        print(
            "\n{}{}{}{}{}Last Visit".format(
                fit("ID", 8),
                fit("Type", 12),
                fit("Mother", 22),
                fit("Child", 22),
                fit("Phone", 16),
            )
        )
        print("-" * 92)

        for p in patient_list:
            child = "-" if p.is_antenatal() else p.child_name
            print(
                f"{fit(p.patient_id, 8)}{fit(p.care_type, 12)}"
                f"{fit(p.name, 22)}{fit(child, 22)}{fit(p.phone, 16)}"
                f"{p.last_visit_label()}"
            )
        print(f"\nTotal patients: {len(patient_list)}")

    # ------------------------------------------------------------------
    # Patient records
    # ------------------------------------------------------------------
    def create_patient(
        self, care_type, mother_name, child_name, phone, address, password
    ):
        patient_id = Patient.generate_patient_id(self.patient_counter)
        self.patient_counter += 1

        # Vaccines are for the baby, so antenatal patients start with none.
        if care_type == POSTNATAL:
            vaccinations = Vaccination.default_vaccinations()
        else:
            vaccinations = []

        patient = Patient(
            patient_id=patient_id,
            care_type=care_type,
            mother_name=mother_name,
            child_name=child_name,
            phone=phone,
            address=address,
            password=password,
            vaccinations=vaccinations,
        )
        self.patients.append(patient)
        self.save_data()
        return patient

    def register_patient_flow(self, by_staff, care_type=None):
        """Used by staff (by_staff=True) and by patients registering
        themselves (by_staff=False)."""
        print("\n--- Register New Patient ---")

        if care_type is None:
            care_type = self.ask_care_type(allow_back=True)
            if care_type is None:
                return None

        print(f"\nRegistering a {care_type} patient.")

        mother_name = self.ask_name("Enter Mother's Name: ")
        child_name = ""
        if care_type == POSTNATAL:
            child_name = self.ask_name("Enter Child's Name: ")
        phone = self.ask_phone("Enter Phone Number: ")
        address = self.ask_address("Enter Address: ")

        duplicate = self.find_duplicate_patient(mother_name, phone)
        if duplicate is not None:
            print("\nPatient Already Registered!")
            if by_staff:
                print(f"Patient ID: {duplicate.patient_id}")
                print(f"Mother Name: {duplicate.name}")
                if not duplicate.is_antenatal():
                    print(f"Child Name: {duplicate.child_name}")
            else:
                # Do not reveal the ID to someone who is not logged in.
                print(
                    "Please go back and choose Log in. If you forgot your "
                    "ID, type FORGOT when asked for it."
                )
            return None

        if by_staff:
            print("\nAsk the patient to choose a password.")
        password = self.ask_new_password()

        patient = self.create_patient(
            care_type, mother_name, child_name, phone, address, password
        )

        print("\nCongratulations! You have successfully registered.")
        self.print_id_card("PATIENT ID", patient.patient_id)
        if by_staff:
            print(
                "Give this ID to the patient and tell her not to forget it. "
                "She will use it with her password to log in."
            )
        else:
            print(
                "Please do not forget this ID. You will use it with your "
                "password to log in next time."
            )
        return patient

    def select_patient(self):
        patient_id = self.ask_required("\nEnter Patient ID: ")
        patient = self.find_patient_by_id(patient_id)
        if patient is None:
            print("\nNo Such Patient Registered!")
        return patient

    def search_patient(self, full):
        """full=True also shows history and immunizations (health workers)."""
        query = self.ask_required("\nEnter Patient ID or name to search: ")
        lower = query.lower()

        matches = [
            p
            for p in self.patients
            if p.patient_id.lower() == lower
            or lower in p.name.lower()
            or lower in p.child_name.lower()
        ]

        if not matches:
            print("\nNo Such Patient Registered!")
            return

        if len(matches) == 1:
            if full:
                matches[0].display_full_record()
            else:
                matches[0].display_basic()
            return

        print(f"\n{len(matches)} patients found:")
        self.print_patient_table(matches)
        print("Search again with an exact Patient ID to see one record.")

    # ------------------------------------------------------------------
    # Sign up
    # ------------------------------------------------------------------
    def staff_sign_up(self, role):
        print(f"\n--- {role} Sign Up ---")

        if self.staff_signup_locked:
            print("Staff sign-up is locked until the system is restarted.")
            return None

        verified = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            pin = self.ask_hidden("Enter the institution PIN: ")
            if hmac.compare_digest(pin, INSTITUTION_PIN):
                verified = True
                break
            print(
                "Wrong institution PIN. "
                f"Attempts left: {MAX_ATTEMPTS - attempt}"
            )

        if not verified:
            self.staff_signup_locked = True
            print(
                "\nToo many wrong PINs. Staff sign-up is locked until the "
                "system is restarted."
            )
            return None

        name = self.ask_name("Enter your full name: ")
        password = self.ask_new_password()

        staff_id = Staff.generate_staff_id(role, self.staff_counter)
        self.staff_counter += 1

        staff = Staff(staff_id, name, role, password=password)
        self.staff_members.append(staff)
        self.save_data()

        print("\nSign up successful!")
        self.print_id_card("YOUR STAFF ID", staff_id)
        print(
            "Please write this ID down. You need it with your password to "
            "log in."
        )
        self.pause()
        return staff

    def patient_sign_up(self, care_type):
        print(f"\n--- {care_type} Patient Sign Up ---")
        patient = self.register_patient_flow(
            by_staff=False, care_type=care_type
        )
        if patient is not None:
            self.pause()
        return patient

    # ------------------------------------------------------------------
    # Log in
    # ------------------------------------------------------------------
    def staff_login(self, role):
        print(f"\n--- {role} Log In ---")
        staff_id = self.ask_required("Enter your Staff ID: ")

        staff = self.find_staff_by_id(staff_id, role)
        if staff is None:
            print(
                f"\nNo {role} is registered with this ID. "
                "Please sign up first."
            )
            return None

        key = f"{role}:{staff.staff_id.lower()}"
        if key in self.locked_keys:
            print("\nThis account is locked until the system is restarted.")
            return None

        while True:
            password = self.ask_hidden("Enter your password: ")
            if staff.check_password(password):
                self.clear_failures(key)
                print(f"\nWelcome, {staff.name}!")
                return staff

            print("Wrong password.")
            if self.register_failure(key):
                return None

    def recover_patient_id(self):
        """'Forgot my ID': the mother proves who she is with her name,
        address and phone number. Only then is her ID shown."""
        print("\nNo problem. Please confirm your details.")
        name = self.ask_required("Enter your name (mother's name): ")

        key = f"recover:{normalize_text(name)}"
        if key in self.locked_keys:
            print("\nThis option is locked until the system is restarted.")
            return

        address = self.ask_required("Enter your Address: ")
        phone = Person.normalize_phone(
            self.ask_required("Enter your Phone Number: ")
        )

        for patient in self.patients:
            if (
                same_text(patient.name, name)
                and same_text(patient.address, address)
                and patient.phone == phone
            ):
                self.clear_failures(key)
                print(
                    f"\nYour Patient ID is {patient.patient_id}. "
                    "Please keep it safe."
                )
                return

        print("\nThose details do not match any patient.")
        self.register_failure(key)

    def patient_login(self, care_type):
        print(f"\n--- {care_type} Patient Log In ---")

        while True:
            patient_id = self.ask_required(
                "Enter your Patient ID (or type FORGOT if you forgot it): "
            )

            if patient_id.upper() == "FORGOT":
                self.recover_patient_id()
                continue

            patient = self.find_patient_by_id(patient_id)
            if patient is None:
                print(
                    "\nNo patient is registered with this ID. Please sign up "
                    "first, or type FORGOT if you forgot your ID."
                )
                return None
            break

        key = f"patient:{patient.patient_id.lower()}"
        if key in self.locked_keys:
            print("\nThis account is locked until the system is restarted.")
            return None

        while True:
            password = self.ask_hidden("Enter your password: ")
            if patient.check_password(password):
                self.clear_failures(key)
                if patient.care_type != care_type:
                    print(
                        "\nThis ID is registered as a "
                        f"{patient.care_type} patient. Please go back and "
                        f"choose {patient.care_type}."
                    )
                    return None
                print(f"\nWelcome back, {patient.name}!")
                return patient

            print("Wrong password.")
            if self.register_failure(key):
                return None

    # ------------------------------------------------------------------
    # Health worker actions
    # ------------------------------------------------------------------
    def add_visit_note(self, staff):
        patient = self.select_patient()
        if patient is None:
            return

        note = self.ask_required("Enter visit note: ")
        patient.add_visit_note(note, staff.name)
        self.save_data()
        print(f"\nVisit note added for {patient.name} ({patient.patient_id}).")

    def update_immunization(self):
        patient = self.select_patient()
        if patient is None:
            return

        if patient.is_antenatal():
            print(
                f"\n{patient.name} is an Antenatal patient. Immunization "
                "can only be updated after the baby is born."
            )
            return

        while True:
            patient.display_immunization()
            print("\n1. Mark a vaccine as completed")
            print("2. Add a new vaccine")
            print("3. Back")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                self.mark_vaccine_completed(patient)
            elif choice == "2":
                self.add_vaccine(patient)
            elif choice == "3":
                return
            else:
                print("\nInvalid option!")

    def mark_vaccine_completed(self, patient):
        if not patient.vaccinations:
            print("\nNo vaccines to update.")
            return

        print()
        for number, vaccine in enumerate(patient.vaccinations, start=1):
            print(f"{number}. {vaccine.name} - {vaccine.get_status()}")

        entered = self.ask("\nEnter the number of the vaccine: ")
        if not entered.isdigit() or not 1 <= int(entered) <= len(
            patient.vaccinations
        ):
            print("\nInvalid vaccine number!")
            return

        vaccine = patient.vaccinations[int(entered) - 1]
        if vaccine.completed:
            print(f"\n{vaccine.name} is already marked as completed.")
            return

        date_text = self.ask_date_or_today(
            "Date given (DD/MM/YYYY, or press Enter for today): "
        )
        vaccine.mark_completed(date_text)
        self.save_data()
        print(f"\n{vaccine.name} marked as completed.")

    def add_vaccine(self, patient):
        name = self.ask_required("Enter the new vaccine name: ")
        if patient.add_vaccination(name):
            self.save_data()
            print(f"\n{name} added as Due.")
        else:
            print("\nThat vaccine is already on the list.")

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------
    def patient_menu(self, patient):
        # Show the saved details right after logging in or registering.
        patient.display_full_record()

        while True:
            print("\n===== PATIENT MENU =====")
            print(f"Logged in as: {patient.name} ({patient.patient_id})")
            print("1. View my information")
            print("2. View my history")
            print("3. View my immunization status")
            print("4. Log out")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                patient.display_basic()
            elif choice == "2":
                patient.display_history()
            elif choice == "3":
                patient.display_immunization()
            elif choice == "4":
                print("\nYou have been logged out.")
                return
            else:
                print("\nInvalid option!")

    def receptionist_menu(self, staff):
        while True:
            print("\n===== RECEPTIONIST MENU =====")
            print(f"Logged in as: {staff.name} ({staff.staff_id})")
            print("1. Register new patient")
            print("2. View all patients")
            print("3. Search patient")
            print("4. Log out")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                self.register_patient_flow(by_staff=True)
            elif choice == "2":
                self.print_patient_table(self.patients)
            elif choice == "3":
                self.search_patient(full=False)
            elif choice == "4":
                print("\nYou have been logged out.")
                return
            else:
                print("\nInvalid option!")

    def health_worker_menu(self, staff):
        while True:
            print("\n===== HEALTH WORKER MENU =====")
            print(f"Logged in as: {staff.name} ({staff.staff_id})")
            print("1. Register new patient")
            print("2. View all patients")
            print("3. Search patient")
            print("4. View patient history")
            print("5. View immunization status")
            print("6. Add visit note")
            print("7. Update immunization")
            print("8. Log out")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                self.register_patient_flow(by_staff=True)
            elif choice == "2":
                self.print_patient_table(self.patients)
            elif choice == "3":
                self.search_patient(full=True)
            elif choice == "4":
                patient = self.select_patient()
                if patient is not None:
                    patient.display_history()
            elif choice == "5":
                patient = self.select_patient()
                if patient is not None:
                    patient.display_immunization()
            elif choice == "6":
                self.add_visit_note(staff)
            elif choice == "7":
                self.update_immunization()
            elif choice == "8":
                print("\nYou have been logged out.")
                return
            else:
                print("\nInvalid option!")

    # ------------------------------------------------------------------
    # Welcome flow
    # ------------------------------------------------------------------
    def role_entry(self, role):
        care_type = None
        if role == "Patient":
            # As soon as Patient is chosen, ask Antenatal or Postnatal.
            care_type = self.ask_care_type(allow_back=True)
            if care_type is None:
                return

        while True:
            if role == "Patient":
                print(f"\n--- Patient ({care_type}) ---")
            else:
                print(f"\n--- {role} ---")
            print("Please enter:")
            print("1. To log in")
            print("2. To sign up")
            print("3. To go back")

            choice = self.ask("\nChoose an option: ")

            if choice in ("1", "2"):
                logging_in = choice == "1"

                if role == "Patient":
                    if logging_in:
                        patient = self.patient_login(care_type)
                    else:
                        patient = self.patient_sign_up(care_type)
                    if patient is not None:
                        self.patient_menu(patient)
                        return
                else:
                    if logging_in:
                        staff = self.staff_login(role)
                    else:
                        staff = self.staff_sign_up(role)
                    if staff is not None:
                        if role == HEALTH_WORKER:
                            self.health_worker_menu(staff)
                        else:
                            self.receptionist_menu(staff)
                        return
            elif choice == "3":
                return
            else:
                print("\nInvalid option!")

    def exit_system(self):
        self.save_data()
        print("\nYou have exited the system. Enter 0 to turn it on again.")

        while True:
            restart = self.ask("Enter 0: ")
            if restart == "0":
                print("\nSystem turned on again.")
                return
            print("Invalid input! Enter 0 to turn the system on again.")

    def run(self):
        while True:
            print("\n=====================================")
            print("     Hello, welcome to the MCHC")
            print("=====================================")
            print("Please enter:")
            print("1. To use as a Health Worker")
            print("2. To use as a Patient")
            print("3. To use as a Receptionist")
            print("4. To exit")

            choice = self.ask("\nChoose an option: ")
            if choice == "1":
                self.role_entry(HEALTH_WORKER)
            elif choice == "2":
                self.role_entry("Patient")
            elif choice == "3":
                self.role_entry(RECEPTIONIST)
            elif choice == "4":
                self.exit_system()
            else:
                print("\nInvalid option!")


def main():
    system = MCHCSystem()
    try:
        system.run()
    except KeyboardInterrupt:
        print("\n\nProgram stopped. Saving data. Goodbye.")
        system.save_data()


if __name__ == "__main__":
    main()
