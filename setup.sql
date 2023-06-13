DROP TABLE IF EXISTS card_payments CASCADE;
DROP TABLE IF EXISTS collaborations CASCADE;
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
DROP TABLE IF EXISTS bans CASCADE;
DROP TABLE IF EXISTS top_10_orders CASCADE;
DROP TABLE IF EXISTS top_10s CASCADE;
DROP TABLE IF EXISTS logins CASCADE;

CREATE TABLE users (
	id		 BIGSERIAL,
	username	 TEXT NOT NULL,
	password_hash TEXT NOT NULL,
	password_salt TEXT NOT NULL,
	email	 TEXT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE consumers (
	display_name	 TEXT NOT NULL,
	birthday	 DATE NOT NULL,
	register_date DATE NOT NULL,
	users_id	 BIGINT,
	PRIMARY KEY(users_id)
);

CREATE TABLE artists (
	stage_name		 TEXT NOT NULL,
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
	name		 TEXT NOT NULL,
	private		 BOOL NOT NULL,
	consumers_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE prepaid_cards (
	id			 BIGSERIAL,
	number			 TEXT NOT NULL,
	credit			 FLOAT(2) NOT NULL,
	expiration		 DATE NOT NULL,
	administrators_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE songs (
	id		 BIGSERIAL,
	ismn		 TEXT NOT NULL,
	title		 TEXT NOT NULL,
	genre		 TEXT NOT NULL,
	duration	 SMALLINT NOT NULL,
	release_date	 DATE NOT NULL,
	explicit	 BOOL NOT NULL,
	artists_users_id BIGINT NOT NULL,
	publishers_id	 BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE subscriptions (
	id		 BIGSERIAL,
	end_time		 TIMESTAMP NOT NULL,
	price		 FLOAT(2) NOT NULL,
	start_time	 TIMESTAMP NOT NULL,
	consumers_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE comments (
	id		 BIGSERIAL,
	content		 TEXT NOT NULL,
	post_time		 TIMESTAMP NOT NULL,
	comments_id	 BIGINT,
	songs_id		 BIGINT NOT NULL,
	consumers_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE publishers (
	id	 BIGSERIAL,
	name	 TEXT NOT NULL,
	email TEXT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE albums (
	id		 BIGSERIAL,
	title		 TEXT NOT NULL,
	artists_users_id BIGINT NOT NULL,
	PRIMARY KEY(id)
);

CREATE TABLE streams (
	id		 BIGSERIAL,
	stream_time	 TIMESTAMP NOT NULL,
	songs_id		 BIGINT,
	consumers_users_id BIGINT,
	PRIMARY KEY(id,songs_id,consumers_users_id)
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

CREATE TABLE bans (
	id			 BIGSERIAL,
	reason			 TEXT NOT NULL,
	start_time		 TIMESTAMP NOT NULL,
	end_time		 TIMESTAMP,
	manual_unban		 BOOL NOT NULL,
	users_id		 BIGINT,
	administrators_users_id BIGINT NOT NULL,
	PRIMARY KEY(id,users_id)
);

CREATE TABLE top_10_orders (
	position			 SMALLINT NOT NULL,
	stream_count		 BIGINT NOT NULL,
	songs_id			 BIGINT,
	top_10s_consumers_users_id BIGINT,
	PRIMARY KEY(songs_id,top_10s_consumers_users_id)
);

CREATE TABLE top_10s (
	last_updated	 TIMESTAMP NOT NULL,
	consumers_users_id BIGINT,
	PRIMARY KEY(consumers_users_id)
);

CREATE TABLE logins (
	id	 BIGSERIAL,
	login_time TIMESTAMP NOT NULL,
	ip	 TEXT NOT NULL,
	users_id	 BIGINT,
	PRIMARY KEY(id,users_id)
);

CREATE TABLE card_payments (
	id		 BIGSERIAL,
	amount_used	 FLOAT(2) NOT NULL,
	payment_time	 TIMESTAMP NOT NULL,
	subscriptions_id BIGINT,
	prepaid_cards_id BIGINT,
	PRIMARY KEY(id,subscriptions_id,prepaid_cards_id)
);

CREATE TABLE collaborations (
	songs_id	 BIGINT,
	artists_users_id BIGINT,
	PRIMARY KEY(songs_id,artists_users_id)
);

ALTER TABLE users ADD UNIQUE (username, email);
ALTER TABLE consumers ADD CONSTRAINT consumers_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE artists ADD CONSTRAINT artists_fk1 FOREIGN KEY (publishers_id) REFERENCES publishers(id);
ALTER TABLE artists ADD CONSTRAINT artists_fk2 FOREIGN KEY (administrators_users_id) REFERENCES administrators(users_id);
ALTER TABLE artists ADD CONSTRAINT artists_fk3 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE administrators ADD CONSTRAINT administrators_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE playlists ADD UNIQUE (name, consumers_users_id);
ALTER TABLE playlists ADD CONSTRAINT playlists_fk1 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE prepaid_cards ADD UNIQUE (number);
ALTER TABLE prepaid_cards ADD CONSTRAINT prepaid_cards_fk1 FOREIGN KEY (administrators_users_id) REFERENCES administrators(users_id);
ALTER TABLE songs ADD UNIQUE (ismn);
ALTER TABLE songs ADD UNIQUE (title, artists_users_id);
ALTER TABLE songs ADD CONSTRAINT songs_fk1 FOREIGN KEY (artists_users_id) REFERENCES artists(users_id);
ALTER TABLE songs ADD CONSTRAINT songs_fk2 FOREIGN KEY (publishers_id) REFERENCES publishers(id);
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_fk1 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE comments ADD CONSTRAINT comments_fk1 FOREIGN KEY (comments_id) REFERENCES comments(id) ON DELETE CASCADE;
ALTER TABLE comments ADD CONSTRAINT comments_fk2 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE comments ADD CONSTRAINT comments_fk3 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE publishers ADD UNIQUE (email);
ALTER TABLE albums ADD CONSTRAINT albums_fk1 FOREIGN KEY (artists_users_id) REFERENCES artists(users_id);
ALTER TABLE albums ADD UNIQUE (title, artists_users_id);
ALTER TABLE streams ADD CONSTRAINT streams_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE streams ADD CONSTRAINT streams_fk2 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE album_orders ADD UNIQUE (position, albums_id);
ALTER TABLE album_orders ADD CONSTRAINT album_orders_fk1 FOREIGN KEY (albums_id) REFERENCES albums(id);
ALTER TABLE album_orders ADD CONSTRAINT album_orders_fk2 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE playlist_orders ADD UNIQUE (position, playlists_id);
ALTER TABLE playlist_orders ADD CONSTRAINT playlist_orders_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE playlist_orders ADD CONSTRAINT playlist_orders_fk2 FOREIGN KEY (playlists_id) REFERENCES playlists(id) ON DELETE CASCADE;
ALTER TABLE bans ADD CONSTRAINT bans_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE bans ADD CONSTRAINT bans_fk2 FOREIGN KEY (administrators_users_id) REFERENCES administrators(users_id);
ALTER TABLE top_10_orders  ADD UNIQUE (position, top_10s_consumers_users_id);
ALTER TABLE top_10_orders ADD CONSTRAINT top_10_orders_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE top_10_orders ADD CONSTRAINT top_10_orders_fk2 FOREIGN KEY (top_10s_consumers_users_id) REFERENCES top_10s(consumers_users_id) ON DELETE CASCADE;
ALTER TABLE top_10s ADD CONSTRAINT top_10s_fk1 FOREIGN KEY (consumers_users_id) REFERENCES consumers(users_id);
ALTER TABLE logins ADD CONSTRAINT logins_fk1 FOREIGN KEY (users_id) REFERENCES users(id);
ALTER TABLE card_payments ADD CONSTRAINT card_payments_fk1 FOREIGN KEY (subscriptions_id) REFERENCES subscriptions(id);
ALTER TABLE card_payments ADD CONSTRAINT card_payments_fk2 FOREIGN KEY (prepaid_cards_id) REFERENCES prepaid_cards(id);
ALTER TABLE collaborations ADD CONSTRAINT collaborations_fk1 FOREIGN KEY (songs_id) REFERENCES songs(id);
ALTER TABLE collaborations ADD CONSTRAINT collaborations_fk2 FOREIGN KEY (artists_users_id) REFERENCES artists(users_id);

DROP TRIGGER IF EXISTS top10_trigger ON streams;
DROP FUNCTION IF EXISTS update_top10();

CREATE FUNCTION update_top10() RETURNS TRIGGER
LANGUAGE plpgSQL
AS $$
DECLARE
    distinct_streamed INTEGER;
BEGIN
    SELECT COUNT(DISTINCT songs_id) INTO distinct_streamed
    FROM streams
    WHERE consumers_users_id = NEW.consumers_users_id;

    -- Check if the user has streamed at least 10 distinct songs
    IF distinct_streamed >= 10 THEN

		-- Delete the old top 10 (the orders cascade delete)
		DELETE FROM top_10s
		WHERE consumers_users_id = NEW.consumers_users_id;

		-- Create the new top 10
		INSERT INTO top_10s(consumers_users_id, last_updated)
		VALUES (NEW.consumers_users_id, current_timestamp);

		-- Create the new top 10 order
		WITH streamed_songs AS
		(
			SELECT songs_id, COUNT(*) AS stream_count
			FROM streams
			WHERE consumers_users_id = NEW.consumers_users_id
			GROUP BY songs_id
			ORDER BY stream_count DESC
			LIMIT 10
		),
		ordered_songs AS
		(
			SELECT ROW_NUMBER() OVER (ORDER BY stream_count DESC, RANDOM()) AS position, songs_id
			FROM streamed_songs
		)
		INSERT INTO top_10_orders (position, songs_id, stream_count, top_10s_consumers_users_id)
		SELECT ordered_songs.position, ordered_songs.songs_id, streamed_songs.stream_count, NEW.consumers_users_id
		FROM streamed_songs
		JOIN ordered_songs ON streamed_songs.songs_id = ordered_songs.songs_id;


    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER top10_trigger
AFTER INSERT ON streams
FOR EACH ROW
EXECUTE FUNCTION update_top10();