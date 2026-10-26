CREATE TABLE patients (
  patient_id SERIAL PRIMARY KEY,
  full_name VARCHAR(120) NOT NULL,
  email VARCHAR(200) NOT NULL UNIQUE,
  phone VARCHAR(30),
  date_of_birth DATE NOT NULL,
  postcode VARCHAR(10) NOT NULL,
  sex CHAR(1) NOT NULL CHECK (sex IN ('F', 'M', 'X'))
);
CREATE TABLE appointments (
  appointment_id SERIAL PRIMARY KEY,
  patient_id INT NOT NULL REFERENCES patients(patient_id),
  clinic VARCHAR(40) NOT NULL CHECK (clinic IN ('cardiology', 'dermatology', 'oncology', 'orthopaedics', 'general')),
  booked_at TIMESTAMP NOT NULL,
  seen_at TIMESTAMP,
  CHECK (seen_at IS NULL OR seen_at >= booked_at)
);
CREATE TABLE prescriptions (
  prescription_id SERIAL PRIMARY KEY,
  appointment_id INT NOT NULL REFERENCES appointments(appointment_id),
  drug_code VARCHAR(12) NOT NULL,
  quantity INT NOT NULL CHECK (quantity > 0 AND quantity <= 180)
);
