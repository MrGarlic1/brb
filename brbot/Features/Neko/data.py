from brbot.Shared.Neko.models import NekoRarity

NEKO_ROLL_CHANCES = {
    NekoRarity.SS: 0.005,
    NekoRarity.S: 0.045,
    NekoRarity.A: 0.20,
    NekoRarity.B: 0.75,
}

NEKO_COLORS = {
    NekoRarity.SS: 0xFF2462,
    NekoRarity.S: 0xFFF27A,
    NekoRarity.A: 0xC666E3,
    NekoRarity.B: 0x3B49D1,
}

NEKO_HOURLY_ROLLS = 5
