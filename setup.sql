DROP TABLE IF EXISTS subscriptions_prepaid_cards CASCADE;
DROP TABLE IF EXISTS artists_songs CASCADE;
DROP TABLE IF EXISTS playlist_orders CASCADE;
DROP TABLE IF EXISTS album_orders CASCADE;
DROP TABLE IF EXISTS streams CASCADE;
DROP TABLE IF EXISTS albums CASCADE;
DROP TABLE IF EXISTS comments CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS songs CASCADE;
DROP TABLE IF EXISTS prepaid_cards CASCADE;
DROP TABLE IF EXISTS playlists CASCADE;
DROP TABLE IF EXISTS administrators CASCADE;
DROP TABLE IF EXISTS artists CASCADE;
DROP TABLE IF EXISTS consumers CASCADE;
DROP TABLE IF EXISTS publishers CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
	id	 BIGSERIAL,
	username VARCHAR(512) NOT NULL,
	password VARCHAR(512) NOT NULL,
	email	 VARCHAR(512) NOT NULL,
	birthday DATE NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE consumers (
	users_id BIGINT,
	PRIMARY KEY(users_id)
);

CREATE TABLE artists (
	publishers_id		 BIGINT NOT NULL,
	administrators_users_id BIGINT NOT NULL,
	users_id		 BIGINT,
	PRIMARY KEY(users_id)
);

CREATE TABLE administrators (
	users_id BIGINT,
	PRIMARY KEY(users_id)
);

CREATE TABLE playlists (
	id		 BIGSERIAL,
	name		 VARCHAR(512) NOT NULL,
	private		 BOOL NOT NULL,
	consumers_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE prepaid_cards (
	id			 VARCHAR(16),
	credit			 SMALLINT NOT NULL,
	expiration		 DATE NOT NULL,
	administrators_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE songs (
	id		 BIGSERIAL,
	ismn		 SMALLINT NOT NULL,
	title		 VARCHAR(512) NOT NULL,
	genre		 VARCHAR(512) NOT NULL,
	duration	 SMALLINT NOT NULL,
	release_date	 DATE NOT NULL,
	explicit	 BOOL NOT NULL,
	artists_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE subscriptions (
	id		 BIGSERIAL,
	end_date		 DATE NOT NULL,
	period		 VARCHAR(512) NOT NULL,
	price		 SMALLINT NOT NULL,
	start_date	 TIMESTAMP NOT NULL,
	consumers_users_id BIGINT,
	PRIMARY KEY(id,consumers_users_id)
);

CREATE TABLE comments (
	id		 BIGSERIAL,
	content		 TEXT NOT NULL,
	post_date		 TIMESTAMP NOT NULL,
	comments_id	 BIGINT NOT NULL,
	songs_id		 BIGINT NOT NULL,
	consumers_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE publishers (
	id	 BIGSERIAL,
	name	 VARCHAR(512) NOT NULL,
	email VARCHAR(512) NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE albums (
	id		 BIGSERIAL,
	title		 VARCHAR(512) NOT NULL,
	artists_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE streams (
	stream_date	 TIMESTAMP NOT NULL,
	songs_id		 BIGINT,
	consumers_users_id BIGINT,
	PRIMARY KEY(songs_id,consumers_users_id)
);

CREATE TABLE album_orders (
	position	 SMALLINT NOT NULL,
	albums_id BIGINT,
	songs_id	 BIGINT,
	PRIMARY KEY(albums_id,songs_id)
);

CREATE TABLE playlist_orders (
	position	 SMALLINT NOT NULL,
	songs_id	 BIGINT,
	playlists_id BIGINT,
	PRIMARY KEY(songs_id,playlists_id)
);

CREATE TABLE artists_songs (
	artists_users_id BIGINT,
	songs_id	 BIGINT,
	PRIMARY KEY(artists_users_id,songs_id)
);

CREATE TABLE subscriptions_prepaid_cards (
	subscriptions_id		 BIGINT,
	subscriptions_consumers_users_id BIGINT,
	prepaid_cards_id		 VARCHAR(16),
	PRIMARY KEY(subscriptions_id,subscriptions_consumers_users_id,prepaid_cards_id)
);

ALTER TABLE users ADD UNIQUE (username);
ALTER TABLE users ADD UNIQUE (email);
ALTER TABLE consumers ADD CONSTRAINT consumers_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE artists ADD CONSTRAINT artists_fk1 FOREIGN KEY (publishers_id) REFERENCES publishers(id);
ALTER TABLE artists ADD CONSTRAINT artists_fk2 FOREIGN KEY (administrators_users_id) REFERENCES administrators(users_id);
ALTER TABLE artists ADD CONSTRAINT artists_fk3 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE administrators ADD CONSTRAINT administrators_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE playlists ADD CONSTRAINT playlists_fk1 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE prepaid_cards ADD CONSTRAINT prepaid_cards_fk1 FOREIGN KEY (administrators_users_id) REFERENCES administrators(users_id);
ALTER TABLE songs ADD UNIQUE (ismn);
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_fk1 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE comments ADD CONSTRAINT comments_fk1 FOREIGN KEY (comments_id) REFERENCES comments(id);
ALTER TABLE comments ADD CONSTRAINT comments_fk2 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE comments ADD CONSTRAINT comments_fk3 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE publishers ADD UNIQUE (email);
ALTER TABLE albums ADD CONSTRAINT albums_fk1 FOREIGN KEY (artists_users_id) REFERENCES artists(users_id);
ALTER TABLE streams ADD CONSTRAINT streams_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE streams ADD CONSTRAINT streams_fk2 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE album_orders ADD CONSTRAINT album_orders_fk1 FOREIGN KEY (albums_id) REFERENCES albums(id);
ALTER TABLE album_orders ADD CONSTRAINT album_orders_fk2 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE playlist_orders ADD CONSTRAINT playlist_orders_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE playlist_orders ADD CONSTRAINT playlist_orders_fk2 FOREIGN KEY (playlists_id) REFERENCES playlists(id);
ALTER TABLE artists_songs ADD CONSTRAINT artists_songs_fk1 FOREIGN KEY (artists_users_id) REFERENCES artists(users_id);
ALTER TABLE artists_songs ADD CONSTRAINT artists_songs_fk2 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE subscriptions_prepaid_cards ADD CONSTRAINT subscriptions_prepaid_cards_fk1 FOREIGN KEY (subscriptions_id, subscriptions_consumers_users_id) REFERENCES subscriptions(id, consumers_users_id);
ALTER TABLE subscriptions_prepaid_cards ADD CONSTRAINT subscriptions_prepaid_cards_fk2 FOREIGN KEY (prepaid_cards_id) REFERENCES prepaid_cards(id);