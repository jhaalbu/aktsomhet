"""Build actual 2 km road buffers and intersect NVE's 1 km grid."""
import json
import math
from pathlib import Path
import pandas as pd
import shapely
from shapely.geometry import box
from pyproj import CRS, Transformer
from shapely.ops import transform

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed'
SIZE=1000
WEST, NORTH, COLS, ROWS=-75000,8000000,1195,1550


def main():
    segments=pd.read_csv(OUT/'vegsegment.csv')
    # NVDB 5973 is ETRS89 / UTM33 + vertical height; strip Z, same horizontal CRS.
    assert set(segments.srid)=={5973}
    horizontal=CRS.from_epsg(5973).sub_crs_list[0]
    transformer=Transformer.from_crs(horizontal,25833,always_xy=True)
    buffers,links,cells=[],[],{}
    for sid,group in segments.groupby('strekning_id',sort=True):
        geometry=shapely.union_all(shapely.force_2d(shapely.from_wkt(group.geometri_wkt.to_numpy())))
        geometry=transform(transformer.transform,geometry)
        polygon=geometry.buffer(2000,quad_segs=16)
        assert polygon.is_valid and polygon.area>0
        buffers.append(dict(strekning_id=sid,buffer_m=2000,srid=25833,
                            area_m2=polygon.area,geometry_wkb=polygon.wkb))
        xmin,ymin,xmax,ymax=polygon.bounds
        cmin=max(0,math.floor((xmin-WEST)/SIZE))
        cmax=min(COLS-1,math.floor((xmax-WEST)/SIZE))
        rmin=max(0,math.floor((NORTH-ymax)/SIZE))
        rmax=min(ROWS-1,math.floor((NORTH-ymin)/SIZE))
        for row in range(rmin,rmax+1):
            for col in range(cmin,cmax+1):
                x,y=WEST+col*SIZE,NORTH-(row+1)*SIZE
                cell=box(x,y,x+SIZE,y+SIZE)
                if not polygon.intersects(cell):
                    continue
                area=polygon.intersection(cell).area
                if area<=0:
                    continue
                index=row*COLS+col
                links.append(dict(strekning_id=sid,cell_index=index,intersection_m2=area,
                                  area_weight=area/polygon.area))
                cells[index]=dict(cell_index=index,x=x+500,y=y+500,srid=25833)
        if len(buffers)%100==0:
            print(f'Buffers: {len(buffers)}; unique cells: {len(cells)}',flush=True)
    b,l,c=pd.DataFrame(buffers),pd.DataFrame(links),pd.DataFrame(cells.values()).sort_values('cell_index')
    assert len(b)==957
    weights=l.groupby('strekning_id').area_weight.sum()
    assert (weights-1).abs().max()<1e-8
    b.to_parquet(OUT/'strekning_buffer_2km.parquet',index=False)
    l.to_parquet(OUT/'strekning_grid_2km.parquet',index=False)
    c.to_csv(OUT/'nve_gridceller.csv',index=False,encoding='utf-8-sig')
    report=dict(buffer_m=2000,sections=len(b),unique_cells=len(c),section_cell_links=len(l),
                grid_size_m=1000,grid_origin=[WEST,NORTH],grid_shape=[ROWS,COLS],
                index_definition='zero-based row * 1195 + column, northwest origin',
                selection='All grid squares with positive buffer intersection area',
                weighting='Area of grid square inside buffer / buffer area',
                crs='EPSG:25833',max_weight_sum_error=float((weights-1).abs().max()))
    (OUT/'buffer_kvalitetsrapport.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
