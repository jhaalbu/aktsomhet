"""Area-weighted daily road weather, circular wind and trailing 3-day sums."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json
from pathlib import Path
import numpy as np
import pandas as pd
from hent_ver import THEMES,START,WARMUP,END

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/weather'
PARAMETERS={
    'rr':'nedbor_mm', 'sdfsw':'nysnodjupn_cm','tm':'temperatur_c',
    'sd':'snodjupn_cm','windSpeed10m24h06':'vindhastigheit_ms',
    'windDirection10m24h06':'vindretning_grader','gwb_sssrel':'jord_vassmetning_pct'}


def main(themes=None):
    report=json.loads((OUT/'download_report.json').read_text(encoding='utf-8'))
    assert report['complete'] and not report['failed_batches'],'Weather download must finish first'
    dates=pd.date_range(WARMUP,END)
    sections=pd.read_csv(ROOT/'data/processed/strekningar.csv').sort_values('strekning_id')
    sids=sections.strekning_id.tolist()
    sid_index={sid:i for i,sid in enumerate(sids)}
    links=pd.read_parquet(ROOT/'data/processed/strekning_grid_2km.parquet')
    links['section_index']=links.strekning_id.map(sid_index)
    inventory=pd.read_csv(ROOT/'data/processed/nve_gridceller_med_maske.csv')
    support=set(inventory.loc[~inventory.outside_nve_mask,'cell_index'])
    available=links.loc[links.cell_index.isin(support)].groupby('strekning_id').area_weight.sum()
    land_fraction=np.array([available.get(sid,0) for sid in sids],dtype=np.float32)
    folder=OUT/'aggregated'
    folder.mkdir(parents=True,exist_ok=True)
    quality=json.loads((OUT/'aggregation_report.json').read_text()) if themes else {}
    for theme in (themes or THEMES):
        label=PARAMETERS[theme]
        shape=(len(dates),len(sids))
        numerator=np.zeros(shape,dtype=np.float32)
        denominator=np.zeros(shape,dtype=np.float32)
        maximum=np.full(shape,-np.inf,dtype=np.float32)
        cosine=np.zeros(shape,dtype=np.float32) if theme=='windDirection10m24h06' else None
        batches=sorted([r for r in report['batches'] if r['theme']==theme],key=lambda r:r['cells'][0])
        processed=set()
        unsupported=[]
        invalid_records=[]
        for n,batch in enumerate(batches):
            assert not processed.intersection(batch['cells'])
            processed.update(batch['cells'])
            unsupported.extend(batch.get('unsupported_cells',[]))
            frame=pd.read_parquet(ROOT/batch['parquet'])
            batch_dates=pd.DatetimeIndex(frame.pop('dato'))
            positions=dates.get_indexer(batch_dates)
            assert np.all(positions>=0)
            values=frame.to_numpy(dtype=np.float32)
            if theme=='gwb_sssrel':
                # Conservative physical plausibility rule; preserve originals in source files.
                bad=np.isfinite(values)&((values<0)|(values>100))
                ii,jj=np.where(bad)
                if len(ii):
                    invalid_records.append(pd.DataFrame({'dato':batch_dates.to_numpy()[ii],
                        'cell_index':frame.columns.to_numpy()[jj], 'source_value':values[ii,jj],
                        'reason':'soil_saturation_outside_0_100_percent'}))
                    values=values.copy()
                    values[bad]=np.nan
            cols={int(name):j for j,name in enumerate(frame.columns)}
            relevant=links.loc[links.cell_index.isin(cols)]
            selected=sorted(relevant.section_index.unique())
            col_index={s:j for j,s in enumerate(selected)}
            weights=np.zeros((len(cols),len(selected)),dtype=np.float32)
            for r in relevant.itertuples():
                weights[cols[r.cell_index],col_index[r.section_index]]+=r.area_weight
            valid=np.isfinite(values)
            selection=np.ix_(positions,selected)
            denominator[selection]+=valid.astype(np.float32)@weights
            if cosine is not None:
                radians=np.deg2rad(np.nan_to_num(values))
                numerator[selection]+=(np.sin(radians)*valid)@weights
                cosine[selection]+=(np.cos(radians)*valid)@weights
            else:
                numerator[selection]+=np.nan_to_num(values)@weights
                for section in selected:
                    contributing=np.flatnonzero(weights[:,col_index[section]]>0)
                    vals=np.where(valid[:,contributing],values[:,contributing],-np.inf)
                    maximum[positions,section]=np.maximum(maximum[positions,section],vals.max(axis=1))
            if (n+1)%100==0:
                print(f'Aggregate {theme}: {n+1}/{len(batches)}',flush=True)
        assert processed==support,(theme,len(processed),len(support))
        valid_fraction=np.divide(denominator,land_fraction[None,:],out=np.zeros_like(denominator),
                                 where=land_fraction[None,:]>0)
        assert valid_fraction.max()<=1.00001
        valid_fraction=np.clip(valid_fraction,0,1)
        adequate=(denominator>0)&(valid_fraction>=0.8)
        if cosine is not None:
            magnitude=np.hypot(numerator,cosine)
            result=np.mod(np.rad2deg(np.arctan2(numerator,cosine)),360).astype(np.float32)
            adequate&=magnitude>1e-6*denominator
            resultant=np.divide(magnitude,denominator,out=np.full_like(magnitude,np.nan),where=denominator>0)
        else:
            result=np.divide(numerator,denominator,out=np.full_like(numerator,np.nan),where=denominator>0)
            maximum[~adequate]=np.nan
        result[~adequate]=np.nan
        # Daily values and 3-day sums share EXACT date convention returned by GTS.
        rolling=None
        if theme in ['rr','sdfsw']:
            rolling=pd.DataFrame(result).rolling(3,min_periods=3).sum().to_numpy(dtype=np.float32)
        for year in range(2006,2027):
            indices=np.flatnonzero((dates.year==year)&(dates>=START))
            d=dates[indices]
            frame=pd.DataFrame({'strekning_id':np.tile(sids,len(d)),
                                'dato':np.repeat(d,len(sids)),
                                label+'_mean':result[indices].ravel(),
                                label+'_valid_fraction_land':valid_fraction[indices].ravel()})
            if cosine is not None:
                frame[label+'_resultant']=resultant[indices].ravel()
            else:
                frame[label+'_max']=maximum[indices].ravel()
            # Lagged features allow models to exclude the event day's weather.
            prev=result[np.maximum(indices-1,0)].copy()
            prev[indices==0]=np.nan
            frame[label+'_lag1']=prev.ravel()
            if rolling is not None:
                frame[label+'_sum3d']=rolling[indices].ravel()
                prev3=rolling[np.maximum(indices-1,0)].copy()
                prev3[indices==0]=np.nan
                frame[label+'_sum3d_lag1']=prev3.ravel()
            frame.to_parquet(folder/f'{theme}_{year}.parquet',index=False,compression='zstd')
        chosen=result[dates>=START]
        valid_dates=np.flatnonzero(np.isfinite(chosen).any(axis=1))
        requested_dates=dates[dates>=START]
        quality[theme]=dict(parameter=label,section_days=int(chosen.size),
                            valid_section_days=int(np.isfinite(chosen).sum()),
                            missing_fraction=float(np.isnan(chosen).mean()),
                            minimum_mean=float(np.nanmin(chosen)) if len(valid_dates) else None,
                            maximum_mean=float(np.nanmax(chosen)) if len(valid_dates) else None,
                            first_valid_date=str(requested_dates[valid_dates[0]].date()) if len(valid_dates) else None,
                            last_valid_date=str(requested_dates[valid_dates[-1]].date()) if len(valid_dates) else None,
                            unsupported_cell_count=len(set(unsupported)),
                            invalid_range_values=sum(len(f) for f in invalid_records),
                            api_units=sorted({r['unit'] for r in batches if r['unit'] is not None}))
        if invalid_records:
            invalid=pd.concat(invalid_records,ignore_index=True)
            invalid.to_csv(OUT/f'{theme}_invalid_values.csv',index=False,encoding='utf-8-sig')
            quality[theme]['invalid_range_dates']=invalid.dato.dt.strftime('%Y-%m-%d').value_counts().sort_index().to_dict()
            quality[theme]['range_rule']='0 <= soil saturation <= 100 percent; raw values preserved'
        compact={k:v for k,v in quality[theme].items() if k!='invalid_range_dates'}
        print(f'Finished aggregation {theme}: {compact}',flush=True)
    quality['land_mask']=dict(sections_without_land_cells=int((land_fraction==0).sum()),
                              minimum_fraction=float(land_fraction.min()),
                              median_fraction=float(np.median(land_fraction)))
    (OUT/'aggregation_report.json').write_text(json.dumps(quality,indent=2),encoding='utf-8')
    pd.DataFrame({'strekning_id':sids,'nve_land_area_fraction':land_fraction}).to_csv(
        ROOT/'data/processed/strekning_nve_dekning.csv',index=False,encoding='utf-8-sig')
    assemble(sids,land_fraction)


def assemble(sids,land_fraction):
    events=pd.read_csv(ROOT/'data/processed/skred_strekning.csv')
    events['dato']=pd.to_datetime(events.dato)
    events=events.drop_duplicates(['skred_id','strekning_id'])
    daily=events.groupby(['strekning_id','dato']).skred_id.nunique().rename('registrerte_skred')
    kinds={'Stein':'stein','Snø':'sno','Is':'is','Jord/løsmasse':'jord',
           'Flomskred (vann+stein+jord)':'flomskred','Sørpeskred (vann+snø+stein)':'sorpe',
           'Is/stein':'is_stein','Utglidning av veg':'vegutgliding'}
    type_counts={label:events.loc[events.skredtype==kind].groupby(['strekning_id','dato']).skred_id.nunique()
                 for kind,label in kinds.items()}
    type_counts['ukjent']=events.loc[events.skredtype.isna()].groupby(['strekning_id','dato']).skred_id.nunique()
    folder=OUT/'strekning_dogn'
    folder.mkdir(parents=True,exist_ok=True)
    total=0
    for year in range(2006,2027):
        frame=None
        for theme in THEMES:
            part=pd.read_parquet(OUT/'aggregated'/f'{theme}_{year}.parquet')
            if frame is None:
                frame=part
            else:
                assert frame[['strekning_id','dato']].equals(part[['strekning_id','dato']])
                frame=pd.concat([frame,part.drop(columns=['strekning_id','dato'])],axis=1)
        key=pd.MultiIndex.from_frame(frame[['strekning_id','dato']])
        assert key.is_unique
        frame['registrerte_skred']=daily.reindex(key,fill_value=0).to_numpy(dtype=np.int16)
        frame['registrert_skred']=(frame.registrerte_skred>0).astype(np.int8)
        for label,counts in type_counts.items():
            frame[f'skred_{label}_antal']=counts.reindex(key,fill_value=0).to_numpy(dtype=np.int16)
        assert np.array_equal(frame[[f'skred_{label}_antal' for label in type_counts]].sum(axis=1),
                              frame.registrerte_skred)
        frame['nve_land_area_fraction']=frame.strekning_id.map(dict(zip(sids,land_fraction))).astype(np.float32)
        frame.to_parquet(folder/f'{year}.parquet',index=False,compression='zstd')
        total+=len(frame)
        if year==2025:
            frame.loc[frame.strekning_id.isin(sids[:3])].to_csv(OUT/'eksempel_strekning_dogn.csv',index=False,encoding='utf-8-sig')
        print(f'Combined daily dataset {year}: {len(frame)} rows',flush=True)
    assert total==len(sids)*len(pd.date_range(START,END))
    summary=dict(period=[START,END],sections=len(sids),days=len(pd.date_range(START,END)),rows=total,
                  format='Parquet, one file per year',
                  weather_aggregation='Intersection-area weighted; min 80% of NVE-supported land area present',
                  wind_direction='Area-weighted circular mean; resultant magnitude reported',
                  sums='Trailing 3 calendar days, including labelled day; lag1 excludes labelled day',
                  zero_event_count='No registered event in this NVDB extract; not proof of no landslide')
    (OUT/'dataset_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--theme',choices=THEMES,action='append',help='Rebuild a theme, reusing other existing aggregates')
    main(parser.parse_args().theme)
