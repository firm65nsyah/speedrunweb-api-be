-- Seed Data untuk Proyek Speedrun Leaderboard
-- Jalankan file ini di SQL Editor Supabase setelah Proyek Speedrun.sql

-- 1. Insert Users
INSERT INTO users (id, username, display_name, email) VALUES
(1, 'speedy_sam', 'SpeedySam', 'sam@example.com'),
(2, 'chrono_ninja', 'ChronoNinja', 'ninja@example.com'),
(3, 'glitch_master', 'GlitchMaster', 'glitch@example.com')
ON CONFLICT (id) DO NOTHING;

-- 2. Insert Genres
INSERT INTO genres (id, name, creator_id) VALUES
(1, 'Platformer', 1),
(2, 'Action RPG', 1),
(3, 'Metroidvania', 2),
(4, 'Sandbox', 3),
(5, 'FPS', 3)
ON CONFLICT (id) DO NOTHING;

-- 3. Insert Games
INSERT INTO games (id, genre_id, creator_id, name, description) VALUES
(1, 1, 1, 'Super Mario 64', '3D platformer klasik di Nintendo 64.'),
(2, 1, 2, 'Celeste', 'Precision platformer tentang mendaki gunung Celeste.'),
(3, 3, 2, 'Hollow Knight', 'Petualangan serangga di kerajaan Hallownest.'),
(4, 2, 1, 'Elden Ring', 'Action RPG open world karya FromSoftware.'),
(5, 4, 3, 'Minecraft', 'Game sandbox survival dan membangun dunia balok.')
ON CONFLICT (id) DO NOTHING;

-- 4. Insert Categories
INSERT INTO categories (id, game_id, creator_id, name) VALUES
(1, 1, 1, '120 Star'),
(2, 1, 1, '16 Star'),
(3, 2, 2, 'Any%'),
(4, 3, 2, 'Any% (No Major Glitches)'),
(5, 4, 1, 'Any% Unrestricted'),
(6, 5, 3, 'Any% Random Seed')
ON CONFLICT (id) DO NOTHING;

-- 5. Insert Entries (Speedrun Runs)
INSERT INTO entries (id, user_id, category_id, duration, description, video_url) VALUES
(1, 1, 2, 912, 'Run 16 Star dengan rute standar BLJ', 'https://youtube.com/watch?v=sample1'),
(2, 2, 3, 1645, 'Celeste Any% sub 28m', 'https://youtube.com/watch?v=sample2'),
(3, 3, 4, 2040, 'Hollow knight sub 35m clean', 'https://youtube.com/watch?v=sample3')
ON CONFLICT (id) DO NOTHING;
