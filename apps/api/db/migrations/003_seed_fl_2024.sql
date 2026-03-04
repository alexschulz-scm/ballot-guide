-- Seed FL-2024-GEN election row for historical 2024 election data.
INSERT OR IGNORE INTO elections (id, state, election_type, election_date, name, is_historical)
VALUES ('FL-2024-GEN', 'FL', 'general', '2024-11-05', '2024 Florida General Election', 1);
