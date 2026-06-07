SELECT_ACTIVE_BANS = """
                     SELECT a.user_id,
                            a.invoked_by,
                            a.reason,
                            UNIX_TIMESTAMP(a.timestamp)
                     FROM discordbot_mod_actions a
                              JOIN (SELECT user_id, MAX(id) AS max_id
                                    FROM discordbot_mod_actions
                                    WHERE action IN ('testing_ban', 'testing_unban')
                                    GROUP BY user_id) m
                                   ON a.id = m.max_id
                     WHERE a.action = 'testing_ban'
                     ORDER BY a.timestamp DESC
                     """

INSERT_ACTION = """
                INSERT INTO discordbot_mod_actions (user_id, action, reason, invoked_by)
                VALUES (%s, %s, %s, %s)
                """

SELECT_BAN_LOG = """
                 SELECT user_id, action, reason, invoked_by, UNIX_TIMESTAMP(timestamp)
                 FROM discordbot_mod_actions
                 WHERE action IN ('testing_ban', 'testing_unban')
                 ORDER BY id DESC
                 LIMIT 200
                 """
