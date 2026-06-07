change_category = """
                  UPDATE discordbot_tickets
                  SET category = %s
                  WHERE channel_id = %s
                    AND creator_id = %s;
                  """

delete_ticket = """
                DELETE
                FROM discordbot_tickets
                WHERE channel_id = %s
                  AND creator_id = %s;
                """

get_ticket_status = """
                    SELECT locked
                    FROM discordbot_tickets
                    WHERE channel_id = %s;
                    """

create_ticket = """
                INSERT INTO discordbot_tickets (creator_id, channel_id, category)
                VALUES (%s, %s, %s)
                """

get_ticket_num = """
                 SELECT ticket_count
                 FROM discordbot_ticket_count
                 WHERE category = %s;
                 """

update_ticket_num = """
                    INSERT INTO discordbot_ticket_count (category, ticket_count)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE ticket_count = %s;
                    """

check_common_teamranks = """
                         SELECT TRUE
                         FROM record_teamrace
                         WHERE Name = %s
                           AND ID IN (SELECT ID FROM record_teamrace WHERE Name = %s)
                         LIMIT 1;
                         """

rename_query = """
               UPDATE record_race
               SET Name = %s
               WHERE Name = %s
                 AND (Map, Time) NOT IN (SELECT Map, Time
                                         FROM record_teamrace
                                         WHERE Name = %s
                                            OR Name = %s
                                         GROUP BY id
                                         HAVING COUNT(*) > 1);

               UPDATE record_teamrace
               SET Name = %s
               WHERE Name = %s
                 AND (Map, Time) NOT IN (SELECT Map, Time
                                         FROM record_teamrace
                                         WHERE Name = %s
                                            OR Name = %s
                                         GROUP BY id
                                         HAVING COUNT(*) > 1);
               """


