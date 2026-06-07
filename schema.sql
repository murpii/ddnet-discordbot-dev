-- schema.sql  canonical schema for the bot's own tables.
--
-- These are the `discordbot_*` tables the bot writes to. Apply them once
-- against your MariaDB database before first run:
--
--     python -m scripts.init_db          # uses the creds in config.ini
--     -- or --
--     mariadb -u <user> -p <database> < schema.sql
--
-- Every statement uses CREATE TABLE IF NOT EXISTS, so re-running is safe and
-- never touches existing data. NOTE: IF NOT EXISTS only skips a table that
-- already exists -- it does NOT migrate a table whose columns have drifted.
-- This bot has no migration system; if you change a column, alter it by hand
-- and update this file to match.
--
-- Not stored here:
--   * DDNet's live game-stats tables (record_points, record_race, ...) are
--     READ for player profiles but belong to the game database.
--   * Small curated config lists live as committed JSON under data/config/, not
--     in the DB: auto_responses.json and blacklist.json (the auto-response and
--     word-blacklist trigger -> response maps) and guides.json. Volatile per-
--     instance state (ticket scores, tester votes) stays gitignored under its
--     own data/ subfolders.


CREATE TABLE IF NOT EXISTS `discordbot_tickets`
(
    `channel_id` BIGINT UNSIGNED NOT NULL,
    `creator_id` BIGINT UNSIGNED NOT NULL,
    `category`   VARCHAR(255)             DEFAULT NULL,
    `locked`     TINYINT(1)      NOT NULL DEFAULT 0,
    PRIMARY KEY (`channel_id`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;

CREATE TABLE IF NOT EXISTS `discordbot_ticket_count`
(
    `category`     VARCHAR(255) NOT NULL,
    `ticket_count` INT(11)      NOT NULL,
    PRIMARY KEY (`category`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;


CREATE TABLE IF NOT EXISTS `discordbot_playerfinder`
(
    `name`        VARCHAR(255) NOT NULL,
    `expiry_date` DATETIME     NOT NULL,
    `added_by`    VARCHAR(255) NOT NULL,
    `reason`      TEXT         DEFAULT NULL,
    `link`        VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (`name`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;


CREATE TABLE IF NOT EXISTS `discordbot_mod_actions`
(
    `id`         INT AUTO_INCREMENT PRIMARY KEY,
    `user_id`    BIGINT                                                                 NOT NULL,
    `action`     ENUM ('ban','kick','timeout','nickname','testing_ban','testing_unban') NOT NULL,
    `reason`     TEXT                                                                            DEFAULT NULL,
    `invoked_by` VARCHAR(64)                                                                     DEFAULT NULL,
    `timestamp`  TIMESTAMP                                                              NOT NULL DEFAULT current_timestamp(),
    INDEX `idx_user` (`user_id`),
    INDEX `idx_user_action` (`user_id`, `action`)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;
