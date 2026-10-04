"""Independent checks of joins, area-weighted values, lags and 3-day sums."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from hent_ver import START,END

ROOT=Path(__file__).resolve().parents[1]
WEATHER=ROOT/'data/weather'


def main():
    events=pd.read_csv(ROOT/'data/processed/skred.csv')
    links=pd.read_csv(ROOT/'data/processed/skred_strekning.csv')
    sections=pd.read_csv(ROOT/'data/processed/strekningar.csv')
    assert events.skred_id.is_unique
    assert set(links.skred_id)<=set(events.skred_id)
    assert set(links.strekning_id)<=set(sections.strekning_id)
    assert events.dato.between(START,END).all()
    unique=links.drop_duplicates(['skred_id','strekning_id'])
    daily=pd.read_parquet(ROOT/'data/processed/skred_dogn.parquet')
    assert daily.registrerte_skred.sum()==len(unique)
    report=json.loads((WEATHER/'download_report.json').read_text())
    assert report['complete'] and not report['failed_batches']
    total=0
    observed_events=0
    for year in range(2006,2027):
        f=WEATHER/'strekning_dogn'/f'{year}.parquet'
        metadata=pq.read_metadata(f)
        expected_days=len(pd.date_range(max(START,f'{year}-01-01'),min(END,f'{year}-12-31')))
        assert metadata.num_rows==expected_days*len(sections)
        frame=pd.read_parquet(f,columns=['strekning_id','dato','registrerte_skred','registrert_skred',
                                          'jord_vassmetning_pct_mean','jord_vassmetning_pct_max'])
        assert not frame.duplicated(['strekning_id','dato']).any()
        assert (frame.groupby('strekning_id').size()==expected_days).all()
        assert set(frame.strekning_id)==set(sections.strekning_id)
        assert np.array_equal(frame.registrert_skred,frame.registrerte_skred>0)
        for col in ['jord_vassmetning_pct_mean','jord_vassmetning_pct_max']:
            assert frame[col].dropna().between(0,100.00001).all()
        total+=len(frame)
        observed_events+=int(frame.registrerte_skred.sum())
    assert total==len(sections)*len(pd.date_range(START,END))
    assert observed_events==len(unique)
    # Compute one road's precipitation directly from source cell time series.
    bridge=pd.read_parquet(ROOT/'data/processed/strekning_grid_2km.parquet')
    sid='46_EV134_S10'
    area=bridge.loc[bridge.strekning_id==sid].set_index('cell_index').area_weight.to_dict()
    test_dates=pd.date_range('2019-01-01','2019-01-04')
    sums=np.zeros(len(test_dates))
    weights=np.zeros(len(test_dates))
    maxima=np.full(len(test_dates),-np.inf)
    for batch in report['batches']:
        if batch['theme']!='rr':
            continue
        relevant=set(batch['cells'])&set(area)
        if not relevant:
            continue
        frame=pd.read_parquet(ROOT/batch['parquet'],columns=['dato']+[str(i) for i in relevant]).set_index('dato')
        for cell in relevant:
            values=frame.loc[test_dates,str(cell)].to_numpy(dtype=float)
            valid=np.isfinite(values)
            sums+=np.where(valid,values*area[cell],0)
            weights+=valid*area[cell]
            maxima=np.maximum(maxima,np.where(valid,values,-np.inf))
    manual=sums/weights
    actual=pd.read_parquet(WEATHER/'strekning_dogn/2019.parquet')
    actual=actual.loc[actual.strekning_id==sid].set_index('dato')
    assert np.allclose(actual.loc[test_dates,'nedbor_mm_mean'],manual,rtol=1e-5,atol=1e-4)
    assert np.allclose(actual.loc[test_dates,'nedbor_mm_max'],maxima)
    assert np.isclose(actual.loc['2019-01-03','nedbor_mm_sum3d'],manual[:3].sum(),rtol=1e-5)
    assert np.isclose(actual.loc['2019-01-04','nedbor_mm_sum3d_lag1'],manual[:3].sum(),rtol=1e-5)
    assert np.isclose(actual.loc['2019-01-04','nedbor_mm_lag1'],manual[2],rtol=1e-5)
    # Independently verify the actual circular aggregation against source cells.
    sin_sum=cos_sum=0.0
    for batch in report['batches']:
        if batch['theme']!='windDirection10m24h06':
            continue
        relevant=set(batch['cells'])&set(area)
        if not relevant:
            continue
        frame=pd.read_parquet(ROOT/batch['parquet'],columns=['dato']+[str(i) for i in relevant]).set_index('dato')
        for cell in relevant:
            value=frame.loc[pd.Timestamp('2019-01-01'),str(cell)]
            if np.isfinite(value):
                sin_sum+=np.sin(np.deg2rad(float(value)))*area[cell]
                cos_sum+=np.cos(np.deg2rad(float(value)))*area[cell]
    manual_angle=np.rad2deg(np.arctan2(sin_sum,cos_sum))%360
    actual_angle=actual.loc['2019-01-01','vindretning_grader_mean']
    angle_error=abs((actual_angle-manual_angle+180)%360-180)
    assert angle_error<0.001,(manual_angle,actual_angle)
    # Wrap-around must also put two northward directions at north, not south.
    angles=np.deg2rad([359,1])
    circular=np.rad2deg(np.arctan2(np.sin(angles).mean(),np.cos(angles).mean()))%360
    assert min(abs(circular),abs(circular-360))<1e-8
    result=dict(validated=True,section_days=total,event_section_links=len(unique),
                checks=['unique keys and full daily calendar','event counts preserved',
                        'manual source-cell area-weighted precipitation and maximum',
                        '3-day sum and preceding-day lag alignment','manual source-cell circular mean',
                        'circular angle wrap-around','processed soil saturation range 0-100 percent'])
    (WEATHER/'validation_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
