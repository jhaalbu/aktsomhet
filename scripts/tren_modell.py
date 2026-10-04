"""Reproducible temporal and geographic baseline experiment for registered slides."""
import os
os.environ['OMP_NUM_THREADS']='8'
os.environ['OPENBLAS_NUM_THREADS']='1'
import hashlib
import json
import time
from pathlib import Path
from datetime import datetime,timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss,log_loss,precision_recall_curve
from sklearn.linear_model import LogisticRegression
os.environ['MPLCONFIGDIR']=str(Path(__file__).resolve().parents[1]/'models/.mplcache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'models/first_run'
SEED=20261004
THREADS=8
PARAMS=dict(objective='binary',metric='average_precision',n_estimators=600,learning_rate=0.05,num_leaves=31,
            min_child_samples=400,reg_lambda=5.0,colsample_bytree=0.9,subsample=0.8,
            subsample_freq=1,max_bin=127,random_state=SEED,n_jobs=THREADS,
            deterministic=True,force_col_wise=True,verbosity=-1)
LAG=['nedbor_mm_lag1','nysnodjupn_cm_lag1','temperatur_c_lag1','snodjupn_cm_lag1',
     'vindhastigheit_ms_lag1','jord_vassmetning_pct_lag1']
SUM3=['nedbor_mm_sum3d_lag1','nysnodjupn_cm_sum3d_lag1']
COVER=['nedbor_mm_valid_fraction_land','jord_vassmetning_pct_valid_fraction_land',
       'vindhastigheit_ms_valid_fraction_land']


def save_json(file,data):
    file.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def load(write_audit=True):
    columns=['strekning_id','dato','registrert_skred']+LAG+SUM3+COVER+[
        'vindretning_grader_lag1','vindretning_grader_resultant',
        'nedbor_mm_max','nysnodjupn_cm_max']
    parts=[]
    sources=[]
    for year in range(2012,2027):
        file=ROOT/f'data/weather/strekning_dogn/{year}.parquet'
        parts.append(pd.read_parquet(file,columns=columns))
        sources.append(dict(file=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    df=pd.concat(parts,ignore_index=True)
    sections=pd.read_csv(ROOT/'data/processed/strekningar.csv').sort_values('strekning_id')
    sids=sections.strekning_id.tolist()
    n=len(sids)
    assert n==957
    assert np.array_equal(df.strekning_id.to_numpy(),np.tile(sids,len(df)//n))
    day=df.dato.to_numpy()[::n]
    assert np.all(np.diff(day)==np.timedelta64(1,'D'))
    assert np.all(df.dato.to_numpy().reshape(-1,n)==day[:,None])
    x=df[LAG+SUM3].copy()
    for col in COVER+['vindretning_grader_resultant','nedbor_mm_max','nysnodjupn_cm_max']:
        x[col+'_lag1']=df[col].shift(n).astype(np.float32)
    for name in ['nedbor_mm','nysnodjupn_cm']:
        a=df[name+'_lag1'].to_numpy().reshape(-1,n)
        x[name+'_sum7d_lag1']=pd.DataFrame(a).rolling(7,min_periods=7).sum().to_numpy(dtype=np.float32).ravel()
    x['temperatur_endring_lag1']=df.temperatur_c_lag1-df.temperatur_c_lag1.shift(n)
    x['snodjupn_endring_lag1']=df.snodjupn_cm_lag1-df.snodjupn_cm_lag1.shift(n)
    angle=np.deg2rad(df.vindretning_grader_lag1)
    x['vindretning_sin_lag1']=np.sin(angle)
    x['vindretning_cos_lag1']=np.cos(angle)
    doy=df.dato.dt.dayofyear.to_numpy()
    x['arstid_sin']=np.sin(2*np.pi*doy/365.25)
    x['arstid_cos']=np.cos(2*np.pi*doy/365.25)
    x=x.astype(np.float32)
    keep=df.dato>=pd.Timestamp('2013-01-01')
    keys=df.loc[keep,['strekning_id','dato']].reset_index(drop=True)
    keys['month']=keys.dato.dt.month.astype(np.int8)
    y=df.loc[keep,'registrert_skred'].to_numpy(dtype=np.int8)
    x=x.loc[keep].reset_index(drop=True)
    weather=list(x.columns)
    lookup=sections.set_index('strekning_id')
    x['lengde_km']=keys.strekning_id.map(lookup.lengde_m/1000).astype(np.float32)
    x['armandel']=keys.strekning_id.map((lookup.arm_lengde_m/lookup.lengde_m).fillna(0)).astype(np.float32)
    category_codes={'E':0,'R':1,'F':2}
    x['vegkategori']=keys.strekning_id.map(lookup.vegkategori.map(category_codes)).astype(np.int32)
    x['strekning_kode']=keys.strekning_id.map({sid:i for i,sid in enumerate(sids)}).astype(np.int32)
    splits={
        'train':(keys.dato<='2020-12-31').to_numpy(),
        'validation':keys.dato.between('2021-01-01','2022-12-31').to_numpy(),
        'calibration':keys.dato.between('2023-01-01','2023-12-31').to_numpy(),
        'test':(keys.dato>='2024-01-01').to_numpy()}
    assert np.all(sum(splits.values())==1)
    assert not any('skred' in f for f in x.columns)
    assert all(f.endswith('lag1') or f in ['arstid_sin','arstid_cos','lengde_km','armandel','vegkategori','strekning_kode'] for f in x.columns)
    audit={name:dict(rows=int(mask.sum()),positives=int(y[mask].sum()),
                    start=str(keys.loc[mask,'dato'].min().date()),end=str(keys.loc[mask,'dato'].max().date()))
           for name,mask in splits.items()}
    audit_document=dict(splits=audit,weather_features=weather,combined_features=list(x.columns),
              target='At least one registered NVDB 445 event per section and calendar date',
              source_files=sources,section_code_mapping={sid:i for i,sid in enumerate(sids)},
              exclusions='No event counts, same-day weather or full-period historical event totals are features',
              retrospective=True,meteorological_day_alignment='Calendar lags only; operational availability unverified')
    if write_audit:
        save_json(OUT/'data_audit.json',audit_document)
    print('Data splits '+json.dumps(audit),flush=True)
    return keys,y,x,weather,splits,sections


def history_fit(keys,y,mask):
    data=keys.loc[mask,['strekning_id','month']].copy()
    data['y']=y[mask]
    global_rate=float(data.y.mean())
    month=data.groupby('month').y.mean()
    roads=data.groupby('strekning_id').y.agg(['sum','count'])
    rates=(roads['sum']+365*global_rate)/(roads['count']+365)
    counts=data.groupby(['strekning_id','month']).y.agg(['sum','count'])
    prior=np.array([rates.get(s,global_rate)*month.get(m,global_rate)/global_rate for s,m in counts.index])
    estimates=(counts['sum'].to_numpy()+60*prior)/(counts['count'].to_numpy()+60)
    table=counts.reset_index()
    table['score']=estimates
    return global_rate,month,rates,table


def history_predict(model,keys):
    global_rate,month,rates,table=model
    index=pd.MultiIndex.from_frame(keys[['strekning_id','month']])
    mapping=table.set_index(['strekning_id','month']).score
    pred=mapping.reindex(index).to_numpy(dtype=float)
    fallback=keys.strekning_id.map(rates).fillna(global_rate).to_numpy()*keys.month.map(month).to_numpy()/global_rate
    return np.clip(np.where(np.isnan(pred),fallback,pred),1e-8,1-1e-8)


def calibrated(raw,y):
    z=np.log(np.clip(raw,1e-7,1-1e-7)/(1-np.clip(raw,1e-7,1-1e-7))).reshape(-1,1)
    model=LogisticRegression(C=1e6,solver='lbfgs',max_iter=300,random_state=SEED)
    model.fit(z,y)
    a,b=float(model.coef_[0,0]),float(model.intercept_[0])
    if a<=0:
        return dict(a=1.0,b=0.0,enabled=False,reason='Nonpositive fitted calibration slope')
    return dict(a=a,b=b,enabled=True,fit_year=2023,method='sigmoid on raw-score logit, no class weighting')


def apply_cal(raw,parameters):
    raw=np.clip(raw,1e-7,1-1e-7)
    z=parameters['a']*np.log(raw/(1-raw))+parameters['b']
    return 1/(1+np.exp(-np.clip(z,-50,50)))


def evaluate(name,keys,y,score,raw,split,folder):
    date_count=keys.dato.nunique()
    n=len(keys)//date_count
    assert np.all(keys.groupby('dato').size().to_numpy()==n)
    truth=y.reshape(date_count,n)
    scores=score.reshape(date_count,n)
    ties=np.random.default_rng(SEED).permutation(n)
    order=np.lexsort((np.broadcast_to(ties,scores.shape),-scores),axis=1)
    result=dict(model=name,split=split,rows=len(y),days=int(date_count),sections=n,positives=int(y.sum()),
                prevalence=float(y.mean()),average_precision=float(average_precision_score(y,score)),
                roc_auc=float(roc_auc_score(y,score)),brier=float(brier_score_loss(y,score)),
                log_loss=float(log_loss(y,score)),raw_brier=float(brier_score_loss(y,raw)))
    daily=pd.DataFrame({'dato':keys.dato.to_numpy()[::n],'positive_days':truth.sum(axis=1)})
    top=[]
    for k in [5,10,20,50]:
        k=min(k,n)
        selected=np.take_along_axis(truth,order[:,:k],axis=1)
        tp=int(selected.sum())
        result[f'recall_top{k}']=tp/max(1,int(y.sum()))
        result[f'precision_top{k}']=tp/(date_count*k)
        result[f'true_positive_top{k}']=tp
        result[f'false_alerts_top{k}']=date_count*k-tp
        daily[f'tp_top{k}']=selected.sum(axis=1)
        if k==10:
            ids=(np.arange(date_count)[:,None]*n+order[:,:k]).ravel()
            alerts=keys.iloc[ids][['strekning_id','dato']].copy()
            alerts['score']=score[ids]
            alerts['registered_event']=y[ids]
            alerts['rank']=np.tile(np.arange(1,11),date_count)
            alerts.to_csv(folder/f'{name}_{split}_top10.csv',index=False,encoding='utf-8-sig')
    daily.to_csv(folder/f'{name}_{split}_daily.csv',index=False)
    prec,rec,_=precision_recall_curve(y,score)
    # Preserve exact AP in metrics, downsample only the figure curve.
    indices=np.unique(np.r_[np.arange(0,len(rec),max(1,len(rec)//4000)),len(rec)-1])
    pd.DataFrame({'recall':rec[indices],'precision':prec[indices]}).to_csv(folder/f'{name}_{split}_pr.csv',index=False)
    print('Metrics '+json.dumps(result),flush=True)
    return result,daily


def experiment(keys,y,x,weather,splits,sections,geographic=False):
    folder=OUT/('geographic' if geographic else 'temporal')
    folder.mkdir(parents=True,exist_ok=True)
    scope=np.ones(len(y),dtype=bool)
    train_scope=scope.copy()
    if geographic:
        # Geographic choice made only from road coordinates, before seeing test labels.
        # 4 km gap between full section bounding boxes avoids overlapping 2 km buffers.
        held=set(sections.loc[sections.ymin>=6880000,'strekning_id'])
        seen=set(sections.loc[sections.ymax<6876000,'strekning_id'])
        assert held.isdisjoint(seen)
        train_scope=keys.strekning_id.isin(seen).to_numpy()
        scope=keys.strekning_id.isin(held).to_numpy()
        save_json(folder/'geography.json',dict(held_section_ids=sorted(held),training_section_ids=sorted(seen),
                  holdout_rule='section ymin >= 6880000 metres in UTM33',
                  train_rule='section ymax < 6876000 metres in UTM33',
                  gap_m=4000,selected_without_labels=True))
        print(f'Geographic holdout: {len(held)} sections; training region: {len(seen)}',flush=True)
    train=splits['train']&train_scope
    val=splits['validation']&train_scope
    cal=splits['calibration']&train_scope
    tests={'validation':val,'calibration':cal,'test':splits['test']&scope}
    history=history_fit(keys,y,train)
    history[3].to_csv(folder/'historical_frequency.csv',index=False)
    save_json(folder/'historical_prior.json',dict(global_rate=history[0],monthly_rates=history[1].to_dict(),
              section_rates=history[2].to_dict(),section_strength_days=365,section_month_strength_days=60))
    models=['historical_frequency','weather','weather_and_road'] if not geographic else ['historical_frequency','weather_and_road']
    metrics=[]
    daily_results={}
    for name in models:
        print(f'Start {folder.name}/{name}',flush=True)
        features=weather if name=='weather' else list(x.columns)
        if name=='historical_frequency':
            predict=lambda mask:history_predict(history,keys.loc[mask])
        else:
            model=lgb.LGBMClassifier(**PARAMS)
            category=[f for f in ['strekning_kode','vegkategori'] if f in features]
            model.fit(x.loc[train,features],y[train],eval_set=[(x.loc[val,features],y[val])],
                      eval_metric='average_precision',categorical_feature=category,
                      callbacks=[lgb.early_stopping(50,first_metric_only=True,verbose=False),lgb.log_evaluation(50)])
            model.booster_.save_model(str(folder/f'{name}.txt'))
            gain=pd.DataFrame({'feature':features,'gain':model.booster_.feature_importance('gain'),
                               'splits':model.booster_.feature_importance('split')}).sort_values('gain',ascending=False)
            gain.to_csv(folder/f'{name}_importance.csv',index=False)
            save_json(folder/f'{name}_metadata.json',dict(features=features,parameters=PARAMS,
                      best_iteration=int(model.best_iteration_),categorical_features=category))
            predict=lambda mask:model.predict_proba(x.loc[mask,features],num_iteration=model.best_iteration_)[:,1]
        cal_raw=predict(cal)
        parameters=calibrated(cal_raw,y[cal])
        save_json(folder/f'{name}_calibration.json',parameters)
        for split,mask in tests.items():
            raw=cal_raw if split=='calibration' else predict(mask)
            score=raw if split=='validation' else apply_cal(raw,parameters)
            # Calibration year is an in-sample calibration diagnostic, not model validation.
            res,daily=evaluate(name,keys.loc[mask],y[mask],score,raw,split,folder)
            metrics.append(res)
            if split=='test':
                daily_results[name]=daily
                pred=keys.loc[mask,['strekning_id','dato']].copy()
                pred['target']=y[mask]
                pred['raw_score']=raw.astype(np.float32)
                pred['score']=score.astype(np.float32)
                pred.to_parquet(folder/f'{name}_test_predictions.parquet',index=False,compression='zstd')
        if name!='historical_frequency':
            del model
    pd.DataFrame(metrics).to_csv(folder/'metrics.csv',index=False)
    save_json(folder/'metrics.json',metrics)
    bootstrap(folder,daily_results)
    draw(folder,metrics)
    return metrics


def bootstrap(folder,daily_results):
    by_month={}
    for name,daily in daily_results.items():
        d=daily.copy()
        d['month']=pd.to_datetime(d.dato).dt.to_period('M').astype(str)
        by_month[name]=d.groupby('month')[['positive_days','tp_top10']].sum()
    first=next(iter(by_month.values()))
    indices=np.random.default_rng(SEED).integers(0,len(first),size=(1000,len(first)))
    samples={}
    result={}
    for name,d in by_month.items():
        assert d.index.equals(first.index)
        a=d.to_numpy()[indices].sum(axis=1)
        values=a[:,1]/np.maximum(a[:,0],1)
        samples[name]=values
        result[name]=dict(recall_top10_ci95=list(map(float,np.quantile(values,[0.025,0.975]))))
    base=samples['historical_frequency']
    for name,values in samples.items():
        if name!='historical_frequency':
            result[name]['difference_vs_history_ci95']=list(map(float,np.quantile(values-base,[0.025,0.975])))
    save_json(folder/'bootstrap.json',dict(block='calendar month',replicates=1000,results=result,
              limitation='Conditional on fitted models; not uncertainty from refitting or registration bias'))


def draw(folder,metrics):
    test=[m for m in metrics if m['split']=='test']
    names={'historical_frequency':'Historisk frekvens','weather':'Vêr og årstid','weather_and_road':'Vêr og veg'}
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    for m in test:
        curve=pd.read_csv(folder/f"{m['model']}_test_pr.csv")
        axes[0].plot(curve.recall,curve.precision,label=f"{names[m['model']]} (AP {m['average_precision']:.3f})")
        axes[1].plot([5,10,20,50],[100*m[f'recall_top{k}'] for k in [5,10,20,50]],marker='o',label=names[m['model']])
    axes[0].axhline(test[0]['prevalence'],color='grey',linestyle=':',label='Grunnfrekvens')
    from matplotlib.ticker import PercentFormatter
    axes[0].set(xlabel='Del registrerte skred-døgn funne',ylabel='Treff blant flagga strekning–døgn',
                title='Precision–recall, sluttest 2024–2026 (utsnitt)',ylim=(0,0.08),xlim=(0,1))
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].xaxis.set_major_formatter(PercentFormatter(1))
    top=max(m[f'recall_top{k}'] for m in test for k in [5,10,20,50])*100
    axes[1].set(xlabel='Strekningar flagga per dag',ylabel='Skred-døgn funne (%)',title='Fast dagleg utval',ylim=(0,min(100,top*1.25)))
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(folder/'evaluation.png',dpi=160)
    fig.savefig(folder/'evaluation.svg')
    plt.close(fig)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    save_json(OUT/'run_config.json',dict(seed=SEED,parameters=PARAMS,started_utc=datetime.now(timezone.utc).isoformat(),
              model_selection='Early stopping on 2021-2022 only; model comparison on same validation',
              calibration='2023 only',test='2024-01-01 through 2026-10-03',
              training_sampling='Full training population, no undersampling or class weighting'))
    keys,y,x,weather,splits,sections=load()
    temporal=experiment(keys,y,x,weather,splits,sections)
    validation=[m for m in temporal if m['split']=='validation']
    chosen=max(validation,key=lambda m:m['recall_top10'])['model']
    save_json(OUT/'model_selection.json',dict(selected_on_validation=chosen,primary_metric='recall_top10',
                                            validation=validation,test_not_used_for_selection=True))
    geographic=experiment(keys,y,x,weather,splits,sections,geographic=True)
    save_json(OUT/'completion.json',dict(complete=True,elapsed_seconds=round(time.monotonic()-start,1),
              selected_on_validation=chosen,temporal=temporal,geographic=geographic,
              completed_utc=datetime.now(timezone.utc).isoformat()))
    print(f'Completed in {time.monotonic()-start:.0f} seconds',flush=True)


if __name__=='__main__':
    main()
