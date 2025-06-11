change_category = """
    UPDATE discordbot_tickets
    SET category = %s
    WHERE channel_id = %s
      AND creator_id = %s;
"""


delete_ticket = """
    DELETE FROM discordbot_tickets
    WHERE channel_id = %s
      AND creator_id = %s;
"""


get_ticket_status = """
    SELECT inactivity_count, locked
    FROM discordbot_tickets
    WHERE channel_id = %s;
"""


create_ticket = """
    INSERT INTO discordbot_tickets (creator_id, channel_id, category, inactivity_count)
    VALUES (%s, %s, %s, 0)
    ON DUPLICATE KEY UPDATE inactivity_count = 0;
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


get_subscriptions = """
    SELECT category 
    FROM discordbot_subscriptions 
    WHERE user_id = %s
"""


add_subscription = """
    INSERT IGNORE INTO discordbot_subscriptions (user_id, category) 
    VALUES (%s, %s);
"""


rm_subscription = """
    DELETE FROM discordbot_subscriptions 
    WHERE user_id = %s
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
      AND (Map, Time) NOT IN (
        SELECT Map, Time 
        FROM record_teamrace 
        WHERE Name = %s OR Name = %s 
        GROUP BY id 
        HAVING COUNT(*) > 1
    );

    UPDATE record_teamrace 
    SET Name = %s 
    WHERE Name = %s 
      AND (Map, Time) NOT IN (
        SELECT Map, Time 
        FROM record_teamrace 
        WHERE Name = %s OR Name = %s 
        GROUP BY id 
        HAVING COUNT(*) > 1
    );
"""


renamed_by = """
    INSERT INTO record_rename (OldName, Name, RenamedBy)
    VALUES (%s, %s, %s);
 """


rm_mapinfo_from_db = """
    DELETE
    FROM discordbot_waiting_maps
    WHERE channel_id = %s;
    
    DELETE
    FROM discordbot_testing_channel_history
    WHERE channel_id = %s;
"""

fetch_map_from_db = """
    SELECT TRUE
    FROM record_maps
    WHERE Map = %s;
"""
