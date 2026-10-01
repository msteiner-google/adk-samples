-- Schema and seed data for the NL2SQL agent's SQLite database.
--
-- Deliberately small and fully deterministic: every golden query has one
-- exact expected result set, so correctness can be checked by comparing rows
-- rather than by judging SQL text.
--
-- The domain matches the rest of the repo (retail banking) so that the same
-- vocabulary works across the document-extraction and NL2SQL agents.

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name   TEXT    NOT NULL,
    city        TEXT    NOT NULL,
    joined_date TEXT    NOT NULL  -- ISO-8601 date
);

CREATE TABLE accounts (
    account_id   INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (customer_id),
    account_type TEXT    NOT NULL,  -- 'checking' | 'savings' | 'credit'
    balance      REAL    NOT NULL,
    opened_date  TEXT    NOT NULL
);

CREATE TABLE transactions (
    transaction_id INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL REFERENCES accounts (account_id),
    amount         REAL    NOT NULL,  -- negative is a debit
    category       TEXT    NOT NULL,
    txn_date       TEXT    NOT NULL
);

INSERT INTO customers (customer_id, full_name, city, joined_date) VALUES
    (1, 'Ada Lovelace',     'London', '2019-03-14'),
    (2, 'Alan Turing',      'London', '2020-06-23'),
    (3, 'Grace Hopper',     'Milan',  '2021-12-09'),
    (4, 'Katherine Johnson','Milan',  '2022-08-26'),
    (5, 'Edsger Dijkstra',  'Zurich', '2023-05-11');

INSERT INTO accounts (account_id, customer_id, account_type, balance, opened_date) VALUES
    (101, 1, 'checking', 2500.00,  '2019-03-20'),
    (102, 1, 'savings',  18000.00, '2019-04-02'),
    (103, 2, 'checking', 640.50,   '2020-07-01'),
    (104, 3, 'savings',  7250.75,  '2022-01-15'),
    (105, 3, 'credit',   -1200.00, '2022-02-01'),
    (106, 4, 'checking', 3100.25,  '2022-09-05'),
    (107, 5, 'savings',  42000.00, '2023-05-20');

INSERT INTO transactions (transaction_id, account_id, amount, category, txn_date) VALUES
    (1001, 101, -45.20,   'groceries',  '2024-01-05'),
    (1002, 101, -120.00,  'utilities',  '2024-01-11'),
    (1003, 101, 2200.00,  'salary',     '2024-01-25'),
    (1004, 102, 500.00,   'transfer',   '2024-01-26'),
    (1005, 103, -18.75,   'groceries',  '2024-02-03'),
    (1006, 103, -62.40,   'transport',  '2024-02-14'),
    (1007, 104, 1500.00,  'transfer',   '2024-02-20'),
    (1008, 105, -340.10,  'travel',     '2024-03-02'),
    (1009, 105, -89.99,   'groceries',  '2024-03-08'),
    (1010, 106, -210.00,  'utilities',  '2024-03-15'),
    (1011, 106, 3000.00,  'salary',     '2024-03-25'),
    (1012, 107, -1250.00, 'travel',     '2024-04-01'),
    (1013, 107, 4000.00,  'salary',     '2024-04-25');
