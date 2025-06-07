import json
import os
import random
from io import BytesIO

import discord
from discord.ext import commands


class Quiz:
    def __init__(self):
        self.answer = ...
        self.question = ...
        self.difficulty = ...

        self.unveiled_indices = set()

    async def quiz_image(self):
        m_root = "data/events/teeguesser/maps"

        diff_dir = [
            f for f in os.listdir(m_root) if os.path.isdir(os.path.join(m_root, f))
        ]

        weights = {
            "insane": 0.24,
            "brutal": 0.03,
            "moderate": 0.2,
            "novice": 0.1,
            "solo": 0.05,
            "oldschool": 0.1,
            "fun": 0.01,
        }

        while True:
            _diff = random.choices(diff_dir, [weights[f] for f in diff_dir])[0]
            if _diff != self.difficulty:
                break

        self.difficulty = _diff
        path_to_diff = os.path.join(m_root, _diff)

        map_dir = [
            f
            for f in os.listdir(path_to_diff)
            if os.path.isdir(os.path.join(path_to_diff, f))
        ]
        _map = random.choice(map_dir)
        path_to_map = os.path.join(path_to_diff, _map)

        _img = [f for f in os.listdir(path_to_map) if f.endswith(".png")]
        img = random.choice(_img)

        with open(os.path.join(path_to_map, img), "rb") as image_file:
            _buf = BytesIO(image_file.read())

        return _diff, _buf, _map

    def hint(self):
        if unveiled_indices := [
            i for i in range(len(self.answer)) if i not in self.unveiled_indices
        ]:
            index = random.choice(unveiled_indices)
            self.unveiled_indices.add(index)

        return [
            (
                "_"
                if i not in self.unveiled_indices and self.answer[i] != " "
                else self.answer[i]
            )
            for i in range(len(self.answer))
        ]


class Tiebreaker(Quiz):
    ...


class Teeguesser(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scores = {}
        self.score_file = "data/teeguesser/scores.json"
    
    async def write_score(self, user_id, rounds=0, maps=0):
        with open(self.score_file, "r", encoding="utf-8") as file:
            self.scores = json.load(file)

        user_id = str(user_id)
        if user_id in self.scores:
            self.scores[user_id]["rounds_won"] += rounds
            self.scores[user_id]["maps_guessed"] += maps
        else:
            self.scores[user_id] = {"rounds_won": rounds, "maps_guessed": maps}

        with open(self.score_file, "w", encoding="utf-8") as file:
            json.dump(self.scores, file)
            
    async def get_score(self, user_id):
        with open(self.score_file, "r", encoding="utf-8") as file:
            self.scores = json.load(file)

        if user_id in self.scores:
            user_data = self.scores[user_id]
            rounds_won = user_data.get("rounds_won")
            maps_guessed = user_data.get("maps_guessed")
            return rounds_won, maps_guessed

        return 0, 0

