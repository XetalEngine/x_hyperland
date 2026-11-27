#!/usr/bin/env python3
"""Cut the supplied avatar sheets at their actual (uneven) cell boundaries.

Inputs stay outside the install payload. Each output records its source hash and
crop rectangle; the original animated account GIF is copied without conversion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
 ('Hats','Fedora|Cowboy hat|Red cap|Blue beanie|Wizard hat|Sun hat|Top hat|Beret|Aviator hat'),
 ('Watches','Classic watch|Gold chronograph|Digital watch|Sport watch|Pocket watch|Skeleton watch|Orange watch|Dress watch|Smartwatch'),
 ('Hands','Open palm|Back of hand|Thumbs up|Peace sign|Fist|Waving hand|Open hand|Pointing hand|Okay hand|Offering hand'),
 ('Footprints','Left sole|Right sole|Left foot|Right foot|Heel|Foot sole|Relaxed foot|Barefoot pair|Standing feet|Side foot'),
 ('Clocks','Golden alarm|Red alarm|Cuckoo clock|Wall clock|Mantel clock|Hourglass|Digital alarm|Sundial|Ship clock|Grandfather clock'),
 ('Music','Sunburst guitar|Flying V guitar|Acoustic guitar|Bass guitar|Ukulele|Amplifier|Guitar pick|Violin|Saxophone|Microphone'),
 ('Mystic','Silver pentacle|Golden pentacle|Stone pentacle|Crystal pentacle|Celtic ring|Crescent pendant|Crystal ball|Black candle|Star card|Ornate mirror'),
 ('Cats','Ginger cat|Black cat|White cat|Siamese cat|British shorthair|Calico cat|Tuxedo cat|Bengal cat|Silver tabby|Ragdoll cat'),
 ('Dogs','Golden retriever|Husky|German shepherd|Corgi|Dachshund|Dalmatian|Shiba inu|Black labrador|Border collie|Pug'),
 ('Accessories','Sunglasses|Red sneakers|Leather boots|Blue backpack|Skateboard|Roller skate|Racing helmet|Compass pendant|Camera|Studio headphones'),
 ('Space','Saturn|Crescent moon|Comet|Spiral galaxy|Earth|Rocket|Satellite|Space station|Lunar lander|Nebula'),
 ('Transport','Sports hatchback|Red motorcycle|Steam train|Yellow submarine|Red biplane|Moon rover|Sailboat|Camper van|Helicopter|Future car'),
 ('Retro tech','Vintage computer|Mechanical keyboard|Gaming headphones|Game controller|Arcade cabinet|Classic camera|Cassette player|Record player|Handheld console|Vacuum tube'),
 ('Fantasy objects','Amethyst crystals|Spellbook|Potion bottle|Golden key|Lantern|Wizard tower|Treasure chest|Floating island|Fairytale castle|Rune stone'),
 ('Places','Log cabin|Greenhouse|Lighthouse|Treehouse|Windmill|Alpine chalet|Train station|Autumn tea house|Coastal cottage|Observatory'),
 ('Food','Ramen|Pizza slice|Sushi roll|Burger|Pancakes|Ice cream|Croissant|Pink doughnut|Tea cup|Strawberry cake'),
 ('Nature','Bonsai|Waterfall|Terrarium|Flowering cactus|Mountains|Tropical island|Autumn tree|Toadstool|Lotus|Volcano'),
 ('Arts','Paint palette|Fountain pen|Acoustic musician|Trumpet|Drum kit|Clapperboard|Sewing machine|Origami crane|Pottery|Sketchbook'),
 ('Adventure','Brass compass|Hiking backpack|Tent|Hiking boots|Diving helmet|Telescope|Hot air balloon|Treasure map|Binoculars|Campfire'),
 ('Workshop','Engine|Turbocharger|Gears|Toolbox|Robot arm|Microchip|Soldering station|Wrench|Generator|Server rack'),
 ('Animal friends','Red panda|Arctic fox|Otter|Axolotl|Snow leopard|Raccoon|Koala|Capybara|White rabbit|Bear cub'),
 ('Little friends','Penguin|Hedgehog|Sea turtle|Tree frog|Purple octopus|Owl|Happy corgi|Purple cat|Smiling ginger cat|Chameleon'),
 ('Robots','Happy robot|Orange robot|Silver robot|Retro robot|Pearl robot|Mechanical owl|Satellite robot|Neon catbot|Brass robot|Nurse robot'),
 ('Forest magic','Emerald dragon|Purple dragon|Phoenix|Flower fairy|Stone guardian|Mushroom friend|Water spirit|Little ghost|Forest guardian|Crystal creature'),
 ('Space friends','Astronaut|Aviator|Space captain|Purple alien|Green alien|Orange alien|Happy comet|Happy Saturn|Little star|Space explorer'),
 ('People','Teal-haired artist|Coiled-hair friend|Red-haired friend|Silver-haired friend|Braided-hair friend|Curly-haired friend|Dark-haired friend|Bearded friend|Purple-haired friend|Wavy-haired friend'),
 ('Adventurers','Chef|Gardener|Painter|Inventor|Scientist|Firefighter|Pilot|Winter explorer|Young explorer|Knight'),
 ('Wildlife','Raven|Bat|Wolf|Lynx|Panther|Luna moth|Fennec fox|Tiger|Wolf pup|Brown bear'),
 ('Happy nature','Strawberry friend|Sushi friend|Coffee friend|Cactus friend|Sunflower friend|Cloud friend|Moon friend|Acorn friend|Flame friend|Ice friend'),
 ('Storybook','Samurai cat|Little wizard|Space frog|Aviator dragon|Ninja penguin|Explorer fox|Elven deer|Headphone robot|Cyber cat|Firefly robot'),
]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def build(sheets, extras, destination):
    destination.mkdir(parents=True, exist_ok=True)
    icons=[]
    original=ROOT/'config/hypr/theme/assets/account.gif'
    shutil.copyfile(original,destination/'original.gif')
    icons.append(dict(id='original', name='HyperFusion · original', file='original.gif',
                      group='HyperFusion', animated=True, sha256=sha(original)))
    rows=[
        [0,141,285,419,546,679,799,920,1030,1147,1254],
        [0,128,258,401,533,666,790,913,1025,1137,1254],
        [0,136,266,403,537,669,807,945,1057,1148,1254],
    ]
    columns=[
        [0,129,256,382,505,630,757,882,1006,1129,1254],
        [0,139,271,402,518,637,762,886,1013,1137,1254],
        [0,139,264,389,513,634,759,884,1009,1132,1254],
    ]
    provenance=[]
    for sheet_index, sheet in enumerate(sheets):
        with Image.open(sheet) as image:
            if image.size != (1254,1254): raise ValueError('Expected the supplied 1254 × 1254 sheet')
            for row in range(10):
                group,names=GROUPS[sheet_index*10+row];names=names.split('|')
                xs=([0,139,278,418,558,698,838,978,1117,1254]
                    if sheet_index==0 and row<2 else columns[sheet_index])
                assert len(xs)==len(names)+1
                for col,name in enumerate(names):
                    key=name.lower().replace(' ','-').replace('·','').replace('—','-')
                    box=(xs[col]+1,rows[sheet_index][row]+1,xs[col+1]-1,rows[sheet_index][row+1]-1)
                    # Keep the entire item; the Qt picker fits rectangular cells.
                    image.crop(box).convert('RGB').save(destination/(key+'.png'),optimize=True)
                    icons.append(dict(id=key,name=name,file=key+'.png',group=group,animated=False,sha256=sha(destination/(key+'.png'))))
                    provenance.append(dict(id=key,sheet=sheet_index+1,source_sha256=sha(sheet),crop=list(box)))
    for key,name,group,path in extras:
        with Image.open(path) as image:
            image.convert('RGB').resize((256,256),Image.Resampling.LANCZOS).save(destination/(key+'.png'),optimize=True)
        icons.append(dict(id=key,name=name,file=key+'.png',group=group,animated=False,sha256=sha(destination/(key+'.png'))))
        provenance.append(dict(id=key,source='Built-in imagegen',source_sha256=sha(path)))
    assert len(icons)==301 and len({i['id'] for i in icons})==301
    (destination/'icons.json').write_text(json.dumps({'version':1,'icons':icons},indent=2)+'\n')
    (destination/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    (destination/'CREDITS.txt').write_text('HyperFusion account artwork\n\n298 pictures cropped from three sheets supplied by the project owner.\nTwo matching additions created with the built-in imagegen tool.\nThe original HyperFusion animated account GIF is preserved byte-for-byte.\nCrop rectangles and source hashes: provenance.json. Generation prompts: prompts.json.\n')
    return icons

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sheets',nargs=3,type=Path)
    parser.add_argument('--cap',required=True,type=Path);parser.add_argument('--watch',required=True,type=Path)
    args=parser.parse_args()
    build(args.sheets,[('flat-cap','Flat cap','Hats',args.cap),('diver-watch','Diver watch','Watches',args.watch)],ROOT/'config/hypr/account_avatars/assets')
