from discord.channel import DMChannel
from discord.member import Member as DiscordMember
from discord.guild import Guild as DiscordGuild
from discord.user import User as DiscordUser
from typing import List, Optional, ClassVar
from sqlalchemy import ForeignKey
from sqlalchemy import (
    String,
    Boolean,
    BigInteger,
    Float,
    JSON,
    DateTime,
    Integer,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    anilist_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    anilist_username: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    rec_timestamp_manga: Mapped[Optional[DateTime]] = mapped_column(
        DateTime, nullable=True
    )
    rec_timestamp_anime: Mapped[Optional[DateTime]] = mapped_column(
        DateTime, nullable=True
    )
    memberships = relationship("Member", back_populates="user")

    discord_user: ClassVar[Optional[DiscordUser]] = None
    dmchannel: ClassVar[Optional[DMChannel]] = None


class Guild(Base):
    __tablename__ = "guilds"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    members = relationship("Member", back_populates="guild")
    config = relationship("GuildConfig", uselist=False, back_populates="guild")
    bingo_games = relationship("BingoGame", back_populates="guild")
    train_games = relationship("TrainGame", back_populates="guild")

    discord_guild: ClassVar[Optional[DiscordGuild]] = None


class GuildConfig(Base):
    __tablename__ = "guild_configs"
    guild_id: Mapped[int] = mapped_column(
        ForeignKey("guilds.id"), primary_key=True, autoincrement=False
    )
    allow_phrases: Mapped[bool] = mapped_column(Boolean)
    limit_user_responses: Mapped[bool] = mapped_column(Boolean)
    max_user_responses: Mapped[int] = mapped_column(Integer)
    restrict_response_deletion: Mapped[bool] = mapped_column(Boolean)
    guild = relationship("Guild", back_populates="config")


class Member(Base):
    __tablename__ = "members"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    user = relationship("User", back_populates="memberships")
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"))
    guild = relationship("Guild", back_populates="members")
    responses = relationship("Response", back_populates="member")

    __table_args__ = (
        Index("ix_member_guild_id", "guild_id"),
        UniqueConstraint("guild_id", "user_id", name="uq_member_user_guild"),
    )

    discord_member: ClassVar[Optional[DiscordMember]] = None


class Response(Base):
    __tablename__ = "responses"
    id: Mapped[int] = mapped_column(primary_key=True)

    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    trigger: Mapped[str] = mapped_column(String(2000))
    text: Mapped[str] = mapped_column(String(2000))
    is_exact: Mapped[bool] = mapped_column(Boolean)
    member = relationship("Member", back_populates="responses")

    __table_args__ = (
        Index("ix_responses_member_id", "member_id"),
        Index("ix_responses_trigger", "trigger"),
        UniqueConstraint(
            "guild_id", "trigger", "text", name="uq_response_guild_trigger_text"
        ),
    )

    def matches(self, text: str) -> bool:
        return self.trigger.lower() == text.lower() or (
            not self.is_exact and text.lower().__contains__(self.trigger.lower())
        )


class Recommendation(Base):
    __tablename__ = "recommendations"
    media_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    anilist_user_id: Mapped[int] = mapped_column(Integer)
    is_manga: Mapped[bool] = mapped_column(Boolean)
    title: Mapped[str] = mapped_column(String(400))
    score: Mapped[float] = mapped_column(Float)
    genres: Mapped[List[str]] = mapped_column(JSON)
    cover_url: Mapped[str] = mapped_column(String(400))
    mean_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __lt__(self, other):
        return self.score < other.score

    def __eq__(self, other):
        if isinstance(other, Recommendation):
            return other.media_id == self.media_id
        else:
            return other == self.media_id


## BINGO


class BingoGame(Base):
    __tablename__ = "bingo_games"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    date: Mapped[DateTime] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"))
    mode: Mapped[int] = mapped_column(Integer)
    known_entries: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    guild = relationship("Guild", back_populates="bingo_games")
    players = relationship(
        "Player", back_populates="game", cascade="all, delete-orphan"
    )


class BingoPlayer(Base):
    __tablename__ = "bingo_players"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("bingo_games.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    starting_anilist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    done: Mapped[bool] = mapped_column(Boolean)
    donetime: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    shots = relationship(
        "BingoShot", back_populates="player", cascade="all, delete-orphan"
    )
    game = relationship("BingoGame", back_populates="players")
    tiles = relationship(
        "BingoTile", back_populates="player", cascade="all, delete-orphan"
    )
    member = relationship("Member")

    __table_args__ = (Index("ix_bingo_player_game_id", "game_id"),)

    @property
    def anilist_id(self) -> Optional[int]:
        return self.member.user.anilist_id

    @property
    def dmchannel(self) -> Optional[DMChannel]:
        return self.member.user.dmchannel


class BingoTile(Base):
    __tablename__ = "bingo_tiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("bingo_games.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("bingo_players.id"))
    row: Mapped[int] = mapped_column(Integer)
    column: Mapped[int] = mapped_column(Integer)
    tag: Mapped[str] = mapped_column(String(400))
    hit: Mapped[bool] = mapped_column(Boolean)
    player = relationship("BingoPlayer", back_populates="tiles")

    __table_args__ = (
        Index("ix_bingo_tile_game_id_player_id", "game_id", "player_id"),
        Index("ix_bingo_tile_row_column", "row", "column"),
        UniqueConstraint(
            "game_id",
            "player_id",
            "row",
            "column",
            name="uq_bingotile_game_member_row_column",
        ),
    )


class BingoShot(Base):
    __tablename__ = "bingo_shots"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("bingo_players.id"))
    anilist_media_id: Mapped[int] = mapped_column(Integer)
    tag: Mapped[str] = mapped_column(String(400))
    time: Mapped[DateTime] = mapped_column(DateTime)
    hit: Mapped[bool] = mapped_column(Boolean)
    info: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    player = relationship("BingoPlayer", back_populates="shots")

    __table_args__ = (
        Index("ix_bingo_shot_player_id", "player_id"),
        UniqueConstraint("player_id", "tag", name="uq_bingoshot_player_tag"),
    )


## TRAINS


class TrainGame(Base):
    __tablename__ = "train_games"
    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.id"))
    guild = relationship("Guild", back_populates="train_games")
    name: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    board_length: Mapped[int] = mapped_column(Integer)
    board_width: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean)
    known_entries: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tiles = relationship(
        "TrainTile", back_populates="game", cascade="all, delete-orphan"
    )
    items = relationship(
        "TrainItem", back_populates="game", cascade="all, delete-orphan"
    )
    players = relationship(
        "Player", back_populates="game", cascade="all, delete-orphan"
    )
    __table_args__ = (Index("ix_train_game_guild_id", "guild_id"),)

    @property
    def size(self) -> tuple[int, int]:
        return self.board_length, self.board_width


class TrainItem(Base):
    __tablename__ = "train_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(400))
    emoji: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(400))
    uses: Mapped[int] = mapped_column(Integer)
    showinfo: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    cost: Mapped[float] = mapped_column(Float)
    game_id: Mapped[int] = mapped_column(ForeignKey("train_games.id"))
    game = relationship("TrainGame", back_populates="items")
    available: Mapped[bool] = mapped_column(Boolean)
    owner_player_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("train_players.id"), nullable=True
    )
    owner = relationship("TrainPlayer", back_populates="items")


class TrainPlayer(Base):
    __tablename__ = "train_players"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("train_games.id"))
    game = relationship("TrainGame", back_populates="players")
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    tag: Mapped[str] = mapped_column(String(40))
    rails: Mapped[int] = mapped_column(Integer)
    starting_anilist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    score: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    start_tile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("train_tiles.id"), nullable=True
    )
    end_tile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("train_tiles.id"), nullable=True
    )
    current_tile_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("player_tiles.id"), nullable=True
    )
    current_tile = relationship("TrainPlayerTile")
    done: Mapped[bool] = mapped_column(Boolean)
    donetime: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    least_watched_genre: Mapped[Optional[str]] = mapped_column(
        String(400), nullable=True
    )

    shots = relationship(
        "TrainShot", back_populates="player", cascade="all, delete-orphan"
    )
    player_tiles = relationship(
        "TrainPlayerTile", back_populates="player", cascade="all, delete-orphan"
    )
    member = relationship("Member")
    items = relationship("TrainItem", back_populates="owner")

    @property
    def anilist_id(self) -> Optional[int]:
        return self.member.user.anilist_id

    @property
    def dmchannel(self) -> Optional[DMChannel]:
        return self.member.user.dmchannel

    @property
    def current_position(self) -> Optional[tuple[int, int]]:
        if self.current_tile_id is None:
            return None
        return self.current_tile.position


class TrainTile(Base):
    __tablename__ = "train_tiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    row: Mapped[int] = mapped_column(Integer)
    column: Mapped[int] = mapped_column(Integer)
    game_id: Mapped[int] = mapped_column(ForeignKey("train_games.id"))
    resource: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    terrain: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    zone: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    game = relationship("TrainGame", back_populates="tiles")
    player_tiles = relationship("TrainPlayerTile", back_populates="tile")
    # rails: list[str] = None,

    @property
    def position(self) -> tuple[int, int]:
        return self.row, self.column


class TrainPlayerTile(Base):
    __tablename__ = "player_tiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    tile_id: Mapped[int] = mapped_column(ForeignKey("train_tiles.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("train_players.id"))
    player = relationship("TrainPlayer", back_populates="player_tiles")
    tile = relationship("TrainTile", back_populates="player_tiles")
    visible: Mapped[bool] = mapped_column(Boolean)
    has_rail: Mapped[bool] = mapped_column(Boolean)

    __table_args__ = (
        Index("ix_train_player_tile_player_id", "player_id"),
        Index("ix_train_player_tile_tile_id", "tile_id"),
        Index("ix_train_player_tile_player_visible", "player_id", "visible"),
        UniqueConstraint(
            "player_id", "tile_id", name="uq_train_player_tile_player_tile_id"
        ),
    )

    @property
    def position(self) -> tuple[int, int]:
        return self.tile.row, self.tile.column


class TrainShot(Base):
    __tablename__ = "train_shots"
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("train_players.id"))
    anilist_media_id: Mapped[int] = mapped_column(Integer)
    row: Mapped[int] = mapped_column(Integer)
    column: Mapped[int] = mapped_column(Integer)
    info: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    time: Mapped[DateTime] = mapped_column(DateTime)
    player = relationship("TrainPlayer", back_populates="shots")

    __table_args__ = (Index("ix_train_shot_player_id", "player_id"),)

    @property
    def coords(self) -> tuple[int, int]:
        return self.row, self.column
