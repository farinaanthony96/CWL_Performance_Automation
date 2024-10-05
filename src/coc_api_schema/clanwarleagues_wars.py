from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Attack:
    attackerTag: str
    defenderTag: str
    stars: int
    destructionPercentage: int
    order: int
    duration: int

@dataclass
class WarClanMember:
    tag: str
    name: str
    townhallLevel: int
    mapPosition: int
    opponentAttacks: int
    bestOpponentAttack: Optional[Attack] = None
    attacks: Optional[List[Attack]] = None
    
    def __post_init__(self):
        # Only initialize the "attacks" attribute if this member attacked.
        if self.attacks:
            self.attacks = [Attack(**attack) for attack in self.attacks]
        
        # Only initialize the "bestOpponentAttack" attribute if this member
        # was attacked.
        if self.bestOpponentAttack:
            self.bestOpponentAttack = Attack(**self.bestOpponentAttack)
            
    def get_attack(self) -> Attack | None:
        return None if self.attacks is None else self.attacks[0]

@dataclass
class BadgeURLs:
    small: str
    medium: str
    large: str

@dataclass
class WarClan:
    tag: str
    name: str
    badgeUrls: BadgeURLs
    clanLevel: int
    attacks: int
    stars: int
    destructionPercentage: float
    members: List[WarClanMember]
    
    def __post_init__(self):
        self.badgeUrls = BadgeURLs(**self.badgeUrls)
        self.members = [WarClanMember(**member) for member in self.members]
        self.members.sort(key=lambda member: member.mapPosition)
    
    def get_war_member(self, player_tag: str) -> WarClanMember | None:
        for war_member in self.members:
            if war_member.tag == player_tag:
                return war_member
        return None
    
    def get_war_member_map_position(self, player_tag: str) -> int | None:
        for position_index,war_member in enumerate(self.members):
            if war_member.tag == player_tag:
                return position_index + 1
        return None

@dataclass
class CWLWar:
    state: str
    teamSize: int
    preparationStartTime: str
    startTime: str
    endTime: str
    clan: WarClan
    opponent: WarClan
    warStartTime: str
    home_clan_tag: str

    def __post_init__(self):
        self.clan = WarClan(**self.clan)
        self.opponent = WarClan(**self.opponent)
        
        # Make sure our home clan is the "clan" attribute.
        if self.opponent.tag == self.home_clan_tag:
            _ = self.clan
            self.clan = self.opponent
            self.opponent = _
        