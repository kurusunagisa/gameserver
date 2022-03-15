SET FOREIGN_KEY_CHECKS=0;

DROP TABLE IF EXISTS `user`;
DROP TABLE IF EXISTS `room`;
DROP TABLE IF EXISTS `room_member`;

CREATE TABLE `user` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `token` varchar(255) DEFAULT NULL,
  `leader_card_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`)
);

CREATE TABLE `room` (
  `room_id` bigint NOT NULL AUTO_INCREMENT,
  `live_id` INT NOT NULL,
  `joined_user_count` SMALLINT NOT NULL,
  `max_user_count` SMALLINT NOT NULL,
  `is_start` BOOLEAN NOT NULL,
  `time` bigint NOT NULL,
  PRIMARY KEY (`room_id`)
);

CREATE TABLE `room_member` (
 `room_member_id` bigint NOT NULL AUTO_INCREMENT,
 `room_id` bigint NOT NULL,
 `user_id` bigint NOT NULL,
 `select_difficulty` SMALLINT NOT NULL,
 `is_host` BOOLEAN NOT NULL,
 `judge_miss` INT NOT NULL,
 `judge_bad` INT NOT NULL,
 `judge_good` INT NOT NULL,
 `judge_great` INT NOT NULL,
 `judge_perfect` INT NOT NULL,
 `score` INT NOT NULL,
 PRIMARY KEY (`room_member_id`),
 FOREIGN KEY (`room_id`) REFERENCES `room` (`room_id`) ON DELETE CASCADE,
 FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
);

ALTER TABLE `room` ADD INDEX `live_id` (`live_id`);
ALTER TABLE `room` ADD INDEX `is_start` (`is_start`);

ALTER TABLE `room_member` ADD INDEX `room_id` (`room_id`);
ALTER TABLE `room_member` ADD INDEX `user_id` (`user_id`);
ALTER TABLE `room_member` ADD INDEX `score` (`score`);