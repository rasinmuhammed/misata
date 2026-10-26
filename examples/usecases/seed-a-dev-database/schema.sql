CREATE TABLE accounts (
  id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  plan VARCHAR(10) NOT NULL CHECK (plan IN ('free', 'team', 'enterprise')),
  created_at TIMESTAMP NOT NULL
);
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  email VARCHAR(200) NOT NULL UNIQUE,
  role VARCHAR(10) NOT NULL CHECK (role IN ('owner', 'admin', 'member'))
);
CREATE TABLE invoices (
  id SERIAL PRIMARY KEY,
  account_id INT NOT NULL REFERENCES accounts(id),
  amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
  issued_on DATE NOT NULL,
  due_on DATE NOT NULL,
  CHECK (due_on > issued_on)
);
