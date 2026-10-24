CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(30) NOT NULL UNIQUE,
  display_name VARCHAR(30) NOT NULL,
  email VARCHAR NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_settings (
  user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  display_theme VARCHAR NOT NULL DEFAULT 'system'
    CHECK (display_theme IN ('light', 'dark', 'system')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_profiles (
  user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  bio TEXT DEFAULT NULL,
  avatar_url TEXT DEFAULT NULL,
  twitch_url TEXT DEFAULT NULL,
  youtube_url TEXT DEFAULT NULL,
  social_media_url TEXT DEFAULT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE genres (
  id SERIAL PRIMARY KEY,
  creator_id INT REFERENCES users(id) ON DELETE SET NULL,
  latest_editor_id INT REFERENCES users(id) ON DELETE SET NULL,
  name VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE games (
  id SERIAL PRIMARY KEY,
  genre_id INT NOT NULL REFERENCES genres(id),
  creator_id INT REFERENCES users(id) ON DELETE SET NULL,
  latest_editor_id INT REFERENCES users(id) ON DELETE SET NULL,
  name VARCHAR NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE categories (
  id SERIAL PRIMARY KEY,
  game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  creator_id INT REFERENCES users(id) ON DELETE SET NULL,
  latest_editor_id INT REFERENCES users(id) ON DELETE SET NULL,
  name VARCHAR NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE entries (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE SET NULL,
  category_id INT NOT NULL REFERENCES categories(id),
  duration BIGINT NOT NULL CHECK (duration > 0),
  description TEXT,
  video_url TEXT UNIQUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE entry_verifications (
  entry_id INT PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE,
  verifier_id INT REFERENCES users(id) ON DELETE SET NULL,
  verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  note TEXT
);

CREATE TABLE category_moderators (
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category_id INT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, category_id)
);

CREATE TABLE game_administrators (
  user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  game_id INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, game_id)
);