# Frontend Assets

Art assets for the map game. All images use WebP format for optimal size.

## Directory structure

| Directory | Purpose |
|---|---|
| `cards/frames/` | Card frame artwork, mapped by card type (观点卡/情绪卡/漏洞卡/修辞卡) |
| `cards/types/` | Type icon overlays (reserved for future art) |
| `cards/rarity/` | Rarity decoration overlays (reserved for future art) |
| `characters/ai/` | AI avatar artwork (reserved for future art) |
| `portraits/` | Story character portraits (reserved for future art) |
| `ui/hud/` | HUD frames and interface decorations (reserved for future art) |
| `ui/icons/` | Reusable interface icons (reserved for future art) |

## Card type image mapping

Configured in `src/data/cardAssets.ts`:

```text
观点卡 → cards/frames/观点卡.webp
情绪卡 → cards/frames/情绪卡.webp
漏洞卡 → cards/frames/漏洞卡.webp
修辞卡 → cards/frames/修辞卡.webp
```

## Suggested formats for new art

- Card frame: transparent WebP or PNG
- Type icon: SVG or PNG
- Character portrait: transparent PNG or WebP, ~400px height
- AI avatar: SVG, PNG, or WebP
