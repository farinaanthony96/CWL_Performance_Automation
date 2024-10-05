from dataclasses import dataclass
from typing import List


@dataclass
class GroupClanMember:
    tag: str
    name: str
    townHallLevel: int

@dataclass
class BadgeURLs:
    small: str
    large: str
    medium: str

@dataclass
class GroupClan:
    tag: str
    name: str
    clanLevel: int
    badgeUrls: BadgeURLs
    members: List[GroupClanMember]
    
    def __post_init__(self):
        self.badgeUrls = BadgeURLs(**self.badgeUrls)
        self.members = [GroupClanMember(**member) for member in self.members]

@dataclass
class RoundWarTags:
    warTags: List[str]

@dataclass
class CWLGroup:
    state: str
    season: str
    clans: List[GroupClan]
    rounds: List[RoundWarTags]
    
    def __post_init__(self):
        self.clans = [GroupClan(**clan) for clan in self.clans]
        self.rounds = [RoundWarTags(**round) for round in self.rounds]

    def get_clan(self, clan_tag: str) -> GroupClan | None:
        for clan in self.clans:
            if clan.tag == clan_tag:
                return clan
        return None
