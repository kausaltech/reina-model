from colour import Color


ARCHER_STROKE = {
    'default': {
        'color': '#A1A1A1',
        'width': 8,
    },
}

GHG_MAIN_SECTOR_COLORS_FI = {
    'Lämmitys': '#FD4F00',
    'Liikenne': '#FFC61E',
    'Sähkö': '#BD2719',
    'Jätteiden käsittely': '#009246',
    'Teollisuus ja työkoneet': '#F5A3C7',
    'Maatalous': '#FFE977'
}


GHG_MAIN_SECTOR_COLORS = {
    'BuildingHeating': '#fd4f00',
    'Transportation': '#00d7a7',
    'ElectricityConsumption': '#9fc9eb',
    'Waste': '#ffe977',
    'Industry': '#F5A3C7',
    'Agriculture': '#ffc61e'
}

 
HELSINKI_COLORS = {
    'brick': '#bd2719',
    'metro': '#fd4f00',
    'summer': '#ffc61e',
    'coat': '#0072c6',
    'fog': '#9fc9eb',
    'silver': '#dedfe1',
    'gold': '#c2a251',
}

THEME_COLORS = {
    'blue':    '#4E80A6',
    'indigo':  '#4C478F',
    'purple':  '#8849B9',
    'pink':    '#E37D7D',
    'red':     '#A73939',
    'orange':  '#C88217',
    'yellow':  '#F4CE73',
    'green':   '#279A6D',
    'teal':    '#7AD7A4',
    'cyan':    '#4CACB3',
}


def generate_color_scale(base_color, n):
    change = 0.2

    color = Color(base_color)
    lum = color.get_luminance()
    if lum <= 0.6 and lum >= 0.4:
        go_down = n // 2
        go_up = n - go_down - 1
    elif lum > 0.6:
        go_down = n
        go_up = 0
    else:
        go_up = n
        go_down = 0

    out = []
    for i in range(0, go_down):
        lum = lum + (0 - lum) * change
        color.set_luminance(lum)
        out.insert(0, color.hex)
    out.append(base_color)
    for i in range(0, go_up):
        lum = lum + (1 - lum) * change
        color.set_luminance(lum)
        out.append(color.hex)
    return out


if __name__ == '__main__':
    for sec, c in GHG_MAIN_SECTOR_COLORS.items():
        print(sec, c)
        ret = generate_color_scale(c, 4)
        print(ret)
