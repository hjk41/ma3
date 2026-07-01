CREATE TABLE IF NOT EXISTS eval_seed (id int primary key, note text);
INSERT INTO eval_seed (id, note) VALUES (1, 'seed-row') ON CONFLICT DO NOTHING;
