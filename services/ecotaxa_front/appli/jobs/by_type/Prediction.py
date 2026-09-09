# -*- coding: utf-8 -*-
import time
from typing import List, Any, Final, Tuple, Optional, Dict

from flask import render_template, g, redirect, flash, request

from appli import PrintInCharte, gvg, XSSEscape, gvp, app
from appli.jobs.Job import Job
from appli.utils import ApiClient, DecodeEqualList, EncodeEqualList
from to_back.ecotaxa_cli_py import ApiException, ObjectsApi, ObjectSetQueryRsp, ProjectSetColumnStatsModel, \
    ProjectTaxoStatsModel, PredictionReq, PredictionRsp
from to_back.ecotaxa_cli_py.api import ProjectsApi, TaxonomyTreeApi
from to_back.ecotaxa_cli_py.models import TaxonModel, ProjectModel, JobModel


class PredictionJob(Job):
    """
        Prediction, just GUI here, bulk of work subcontracted to back-end.
    """
    UI_NAME: Final = "Prediction"

    OBJECT_VARS: Final = {"depth_max", "depth_min"}

    @classmethod
    def initial_dialog(cls):
        """ In UI/flask, initial load, GET. Also the entry point for every retrain-flow
        navigation link/GET (picking a model, viewing its confirm page) -- only the final
        "start re-training" submit is a POST, handled in create_or_update below. """
        mode = gvg('mode')
        if mode == 'retrain':
            model_name = gvg('modelname', '')
            if model_name == '':
                return cls.workflow_start_page()
            return cls.retrain_confirm_page(model_name)
        if mode != 'new':
            with ApiClient(ProjectsApi, request) as api:
                models = api.get_trained_models(int(gvg("projid")))
            if models:
                # Existing named model(s): let the user choose train-new vs retrain-one,
                # instead of dropping them straight into "train new" as if this were the
                # project's first model.
                return cls.workflow_start_page()
        return cls.base_projects_select_page()

    @classmethod
    def create_or_update(cls):
        """ In UI/flask, submit/resubmit of pages """
        if gvp('mode') == 'retrain':
            # The only POST in the retrain sub-flow: the confirm page's "start re-training"
            # submit. Everything before this (picking a model, viewing the confirm page) is
            # plain GET navigation handled by initial_dialog above.
            return cls.retrain_start_task()
        elif gvp('src', gvg('src')) == "":
            # Source not chosen yet
            return cls.base_projects_select_page()
        elif gvp('learninglimit', gvg('learninglimit')) == "":
            # Source chosen but not categories
            return cls.categories_config_page()
        elif gvp('starttask') != "Y":
            # Source chosen and categories but not features
            return cls.features_config_page()
        elif gvp('teststep') != "Y":
            # Features chosen but not the held-out test split
            return cls.testsplit_config_page()
        else:
            errs = cls.validate_task()
            if len(errs) > 0:
                for e in errs:
                    flash(e, "error")
                return PrintInCharte("<a href='#' onclick='history.back();'>Back</a>")
            # All OK
            return cls.start_task()

    @classmethod
    def get_target_project(cls) -> Tuple[Optional[ProjectModel], str]:
        # The project is in the URL, get it and check access
        prj_id = int(gvg("projid"))
        with ApiClient(ProjectsApi, request) as api:
            try:
                target_prj: ProjectModel = api.project_query(prj_id, for_managing=False)
            except ApiException as ae:
                if ae.status in (401, 403):
                    return None, "ACCESS DENIED for this project"
                else:
                    raise
        # Feed global template values
        g.prjtitle = target_prj.title
        g.headcenter = "<h4><a href='/prj/{0}'>{1}</a></h4>".format(target_prj.projid, XSSEscape(target_prj.title))
        # Compute filters for telling the user
        filters: Dict[str, str] = {}
        filters_html = cls.GetFilterText(cls._extract_filters_from_url(filters, target_prj))
        return target_prj, filters_html

    @classmethod
    def base_projects_select_page(cls):
        # First configuration page, choose base projects
        # This page is called from initial GET or POSTs to iself when project filters are used
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)
        # The page reloads itself (POST) when using the "Search" button
        try:
            # In case the filter box was used, validate it.
            if gvp("filt_featurenbr"):
                filt_featurenbr = int(gvp("filt_featurenbr"))
            else:
                filt_featurenbr = 10
        except ValueError:
            flash("Common features must be an integer", category="error")
            return PrintInCharte("<a href='#' onclick='history.back();'>Back</a>")
        title_filter = gvp('filt_title', '')
        if request.method == "GET":
            instrument_filter = target_prj.instrument
        else:
            instrument_filter = gvp('filt_instrum', '')

        src_projs_str = gvp('srcs', '').split(",")
        src_projs = [int(prj_str) for prj_str in src_projs_str if prj_str.isdigit()]

        # Get previous choices AKA settings which are stored at project level
        settings = DecodeEqualList(target_prj.classifsettings)
        target_features = set(target_prj.obj_free_cols.keys())

        previous_ls = settings.get("baseproject", "")  # a coma-separated list of project IDs
        if previous_ls != "":
            # We can have one or several base projects, which are reminded here
            settings_prj_ids = [int(prj_id) for prj_id in previous_ls.split(",") if prj_id.isdigit()]
        else:
            settings_prj_ids = []

        # Collect information for out-of-table projects as well
        no_tbl_projs = {}  # key: project ID, value: ProjectModel

        # Collect all projects matching the conditions
        usable_proj_list = cls.api_read_accessible_projects(instrument_filter, title_filter)

        # Enrich the list with useful calculations
        filtered_projs = []
        matching_per_proj = {}
        validated_per_proj = {}
        for a_maybe_src_prj in usable_proj_list:
            matching_features = len(set(a_maybe_src_prj.obj_free_cols.keys()) & target_features)
            if matching_features < filt_featurenbr:
                no_tbl_projs[a_maybe_src_prj.projid] = a_maybe_src_prj
                continue
            matching_per_proj[a_maybe_src_prj.projid] = matching_features
            validated = (a_maybe_src_prj.objcount if a_maybe_src_prj.objcount else 0) * \
                        (a_maybe_src_prj.pctvalidated if a_maybe_src_prj.pctvalidated else 0) / 100
            validated_per_proj[a_maybe_src_prj.projid] = validated
            filtered_projs.append(a_maybe_src_prj)

        # Sort to have the most interesting ones in first
        filtered_projs.sort(key=lambda r: (-matching_per_proj[r.projid], -validated_per_proj[r.projid]))
        table_lines = []
        for a_maybe_src_prj in filtered_projs:
            matching = matching_per_proj[a_maybe_src_prj.projid]
            validated = validated_per_proj[a_maybe_src_prj.projid]
            cnn_network_id = a_maybe_src_prj.cnn_network_id if a_maybe_src_prj.cnn_network_id else ""
            if a_maybe_src_prj.projid in src_projs:
                checked = True
                src_projs.remove(a_maybe_src_prj.projid)
            elif a_maybe_src_prj.projid in settings_prj_ids:
                checked = True
            else:
                checked = False
            line = {"checked": checked, "projid": a_maybe_src_prj.projid, "title": a_maybe_src_prj.title,
                    "validated_nb": int(validated), "matching_nb": matching, "deep_model": cnn_network_id,
                    "instrument": a_maybe_src_prj.instrument}
            if not checked:
                table_lines.append(line)
            else:
                table_lines.insert(0, line)

        # Collect project info for missing IDs. We need remaining ALL selected source projects and settings ones
        base_prj_infos = []
        not_found_msg = "(ignored, not found)"
        for a_base_prj_id in settings_prj_ids + src_projs:
            if a_base_prj_id in no_tbl_projs:
                continue
            with ApiClient(ProjectsApi, request) as api:
                try:
                    proj: ProjectModel = api.project_query(a_base_prj_id,
                                                           for_managing=False)
                    no_tbl_projs[a_base_prj_id] = proj
                except ApiException as _ae:
                    # The base project might be gone or not visible to current user
                    base_prj_infos.append((a_base_prj_id, not_found_msg))

        for prj_id in src_projs:
            # Remaining source projects are filtered by display, but still valid in selection
            line = {"checked": True, "projid": prj_id, "title": "⚠️ Filtered ⚠️" + no_tbl_projs[prj_id].title,
                    "validated_nb": "", "matching_nb": "", "deep_model": ""}
            table_lines.insert(0, line)

        return render_template('jobs/prediction_create_lstproj.html',
                               url=request.query_string.decode('utf-8'),
                               prj_table=table_lines,
                               deep_features=target_prj.cnn_network_id,
                               filters_info=filters_html,
                               filt_title=title_filter, filt_features_nbr=filt_featurenbr,
                               filt_instrum=instrument_filter)

    #################################################################################################

    # noinspection PyUnresolvedReferences
    @classmethod
    def final_action(cls, job: JobModel):
        prj_id = job.params["req"]["project_id"]
        model_name = job.params["req"].get("model_name")  # absent on jobs predating naming
        time.sleep(1)
        # TODO: Remove the commented, but for now we have trace information inside
        # DoTaskClean(self.task.id)
        result = job.result or {}
        rowcount = result.get("rowcount")
        ret = "<p>{0} object(s) classified.</p>".format(rowcount) if rowcount is not None else ""
        evaluation = result.get("evaluation")
        if evaluation:
            ret += cls.RenderEvaluation(evaluation)
        # Scoped to this job's own model, not every model in the project, so the chart
        # reads as "this model's versions".
        with ApiClient(ProjectsApi, request) as api:
            history = api.get_training_history(prj_id, model_name=model_name)
        ret += render_template('jobs/_training_history_chart.html',
                              history=history, chart_id="final")
        ret += """<a href='/prj/{0}' class='btn btn-primary btn-sm'  role=button>
        Go to Manual Classification Screen</a> """.format(prj_id)
        return ret

    @classmethod
    def RenderEvaluation(cls, evaluation: dict) -> str:
        overall = evaluation.get("overall_accuracy")
        macro = evaluation.get("macro_accuracy")
        per_taxon = evaluation.get("per_taxon") or []
        excluded = evaluation.get("excluded_categories") or []
        note = evaluation.get("note")

        if not per_taxon:
            msg = note or "Not enough data to evaluate."
            return "<p><b>Evaluation:</b> {0}</p>".format(XSSEscape(msg))

        # Worst accuracy first: the table and the bar chart below share this
        # order, so problem categories are the first thing you see in both.
        sorted_taxon = sorted(per_taxon, key=lambda r: r["accuracy"])

        rows = "".join(
            """<tr><td>{0}</td><td>{1}</td><td>{2} / {3}</td><td>{4:.1f}%</td></tr>""".format(
                XSSEscape(r["name"]), r.get("train_support", 0), r["correct"],
                r["support"], r["accuracy"] * 100
            )
            for r in sorted_taxon
        )
        excluded_note = ""
        if excluded:
            excluded_note = (
                "<p><small>{0} categorie(s) had too few validated objects to be "
                "evaluated (still used for training): {1}</small></p>".format(
                    len(excluded), ", ".join(str(c) for c in excluded)
                )
            )
        return """
        <div style="text-align:left; margin: 1em 0;">
          <h4>Held-out test evaluation</h4>
          <p><b>Overall accuracy: {overall:.1f}%</b> &nbsp; (macro-average: {macro:.1f}%,
          test size: {test_size}, train size: {train_size})</p>
          <table class="table table-striped table-condensed" style="max-width:600px">
            <thead><tr><th>Taxon</th><th>Train images</th><th>Correct / Support</th><th>Accuracy</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          {excluded_note}
          {chart}
        </div>
        """.format(
            overall=(overall or 0) * 100,
            macro=(macro or 0) * 100,
            test_size=evaluation.get("test_size", 0),
            train_size=evaluation.get("train_size", 0),
            rows=rows,
            excluded_note=excluded_note,
            chart=cls.RenderPerTaxonBarChart(sorted_taxon),
        )

    @classmethod
    def RenderPerTaxonBarChart(cls, sorted_taxon: List[dict]) -> str:
        """
        Horizontal bar chart of per-taxon accuracy, one hue (this is a single
        magnitude series, not distinct categories), worst first -- same order
        as the table above it. `sorted_taxon` is already sorted by accuracy.
        """
        bar_rows = "".join(
            """
            <div style="display:flex; align-items:center; gap:8px; height:22px;"
                 title="{name_attr}: {correct}/{support} correct in test, {train} image(s) in training set">
              <div style="width:180px; flex:0 0 180px; font-size:12px; text-align:right;
                          white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{name}</div>
              <div style="position:relative; flex:1 1 auto; height:16px;">
                <div style="position:absolute; left:0; top:0; bottom:0; width:{pct:.2f}%;
                            min-width:2px; background:#337ab7; border-radius:0 4px 4px 0;"></div>
              </div>
              <div style="width:46px; flex:0 0 46px; font-size:12px;
                          font-variant-numeric:tabular-nums;">{pct:.1f}%</div>
            </div>
            """.format(
                name_attr=XSSEscape(r["name"]),
                name=XSSEscape(r["name"]),
                correct=r["correct"],
                support=r["support"],
                train=r.get("train_support", 0),
                pct=r["accuracy"] * 100,
            )
            for r in sorted_taxon
        )
        return """
        <div style="margin-top:1.5em; max-width:700px;">
          <h4>Accuracy by taxon</h4>
          <div style="display:flex; flex-direction:column; gap:2px;">{bar_rows}</div>
        </div>
        """.format(bar_rows=bar_rows)

    #################################################################################################

    @classmethod
    def validate_task(cls):
        target_prj, filters_html = cls.get_target_project()

        src_prj_ids, categories, learning_limit, pre_mapping, obj_vars, use_scn, test_fraction, model_name = \
            cls.get_posted_task_params()

        # Check a bit
        errors = []
        if len(obj_vars) == 0 and use_scn is False:
            errors.append("You must select some variable")
        if len(categories) == 0:
            errors.append("You must select some category")
        if model_name == "":
            errors.append("You must name this model")
        else:
            with ApiClient(ProjectsApi, request) as api:
                existing_models = api.get_trained_models(target_prj.projid)
            if any(m["name"] == model_name for m in existing_models):
                errors.append(
                    "Model name '%s' is already used in this project -- pick another, "
                    "or use Re-train instead" % model_name)

        # Use the API entry point for querying the impacted objects. At this point we just need
        # to know if it's != 0
        with ApiClient(ObjectsApi, request) as api:
            filters = {}
            cls._extract_filters_from_url(filters, target_prj)
            filters["statusfilter"] = "UP"
            res: ObjectSetQueryRsp = api.get_object_set(
                project_id=target_prj.projid,
                project_filters=filters,
                window_size=100)

        if len(res.object_ids) == 0:
            msg = cls.cook_no_object_message(filters)
            errors.append(msg)

        if len(errors) == 0:
            # Save parameters
            sav = {'critvar': gvp("CritVar"),
                   'baseproject': gvp("src"),
                   'seltaxo': gvp("Taxo"),
                   'posttaxomapping': gvp("PostTaxoMapping"),
                   'testfraction': gvp("testfraction", "0")}
            # Update project classification settings
            with ApiClient(ProjectsApi, request) as api:
                api.set_project_predict_settings(project_id=target_prj.projid,
                                                 settings=EncodeEqualList(sav))
        return errors

    @classmethod
    def start_task(cls):
        # Launch Job on back-end
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)
        filters = {}
        cls._extract_filters_from_url(filters, target_prj)

        src_prj_ids, categories, learning_limit, pre_mapping, obj_vars, use_scn, test_fraction, model_name = \
            cls.get_posted_task_params()

        # Prepare back-end call
        req = PredictionReq(project_id=target_prj.projid,
                            model_name=model_name,
                            source_project_ids=src_prj_ids,
                            learning_limit=learning_limit,
                            categories=categories,
                            features=obj_vars,
                            use_scn=use_scn,
                            pre_mapping=pre_mapping,
                            test_fraction=test_fraction)
        # Call and redirect
        with ApiClient(ObjectsApi, request) as api:
            rsp: PredictionRsp = api.predict_object_set({'filters': filters,
                                                         'request': req})
        return redirect("/Job/Monitor/%d" % rsp.job_id)

    @classmethod
    def get_posted_task_params(cls):
        # Extract params into properly formatted vars
        src_prj_ids = [int(prj_id) for prj_id in gvp("src").split(",")]
        use_scn = gvp("usescn") == 'Y'
        learning_limit = int(gvp("learninglimit"))
        # Chosen vars need to be prefixed
        chosen_vars = gvp("CritVar").split(",")
        obj_vars = ["obj." + a_var if a_var in cls.OBJECT_VARS else "fre." + a_var
                    for a_var in chosen_vars]
        if obj_vars == ['fre.']:
            # Tricky case with 0 var
            obj_vars.clear()
        chosen_taxo = gvp("Taxo").split(",")
        categories = [int(classif_id) for classif_id in chosen_taxo]
        pre_taxo_mapping = gvp("PostTaxoMapping")
        if len(pre_taxo_mapping) > 0:
            pre_map_txt = [mpg.split(":") for mpg in pre_taxo_mapping.split(",")]
        else:
            pre_map_txt = []
        pre_mapping = {int(from_): int(to) for from_, to in pre_map_txt}
        # Posted as a 0-50 percentage, PredictionReq wants a 0.0-0.5 fraction
        test_fraction = int(gvp("testfraction", "0") or "0") / 100.0
        model_name = gvp("modelname", "").strip()
        return src_prj_ids, categories, learning_limit, pre_mapping, obj_vars, use_scn, test_fraction, model_name

    @staticmethod
    def api_read_accessible_projects(instrument_filter, title_filter):
        bef = time.time()
        with ApiClient(ProjectsApi, request) as api:
            ret: List[ProjectModel] = api.search_projects(not_granted=False,
                                                          title_filter=title_filter,
                                                          instrument_filter=instrument_filter,
                                                          filter_subset=False)
        with ApiClient(ProjectsApi, request) as api:
            ret.extend(api.search_projects(not_granted=True,
                                           title_filter=title_filter,
                                           instrument_filter=instrument_filter,
                                           filter_subset=False))
        app.logger.info('Get Projects API call duration: %0.3f s', time.time() - bef)
        return ret

    @classmethod
    def api_read_projects(cls, auth: Any, src_prj_ids: List[int], revobjmapbaseByProj, common_features):
        """ Read project's free columns and add them to the common set """
        ret = []
        for src_prj_id in src_prj_ids:
            with ApiClient(ProjectsApi, auth) as api:
                proj: ProjectModel = api.project_query(src_prj_id,
                                                       for_managing=False)
            revobjmapbaseByProj[src_prj_id] = cls.GetAugmentedReverseObjectMap(proj)
            common_features.intersection_update(set(revobjmapbaseByProj[src_prj_id].keys()))
            ret.append(proj)
        return ret

    @classmethod
    def categories_config_page(cls):
        # Configuration of categories for the prediction.
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)

        # Get via API all implied projects
        posted_srcs = gvp('src', gvg('src'))
        src_prj_ids = [int(x) for x in posted_srcs.split(',') if x.isdigit()]
        src_projs = []
        for a_prij_id in src_prj_ids:
            with ApiClient(ProjectsApi, request) as api:
                src_proj: ProjectModel = api.project_query(a_prij_id,
                                                           for_managing=False)
            src_projs.append("#%s - %s" % (src_proj.projid, src_proj.title))
        src_prj_ids_sql = ",".join([str(x) for x in src_prj_ids])  # By chance it's an OK format for the API as well

        # Get the number of validated objects of each category in all source projects
        with ApiClient(ProjectsApi, request) as api:
            stats: List[ProjectTaxoStatsModel] = api.project_set_get_stats(ids=src_prj_ids_sql,
                                                                           taxa_ids="all")
        validated_categ_count = dict()
        for a_stat in stats:
            categ = a_stat.used_taxa[0]  # In this mode, a single taxa in the list
            if a_stat.nb_validated == 0:
                continue
            if categ in validated_categ_count:
                validated_categ_count[categ] += a_stat.nb_validated
            else:
                validated_categ_count[categ] = a_stat.nb_validated

        # Get info on them
        with ApiClient(TaxonomyTreeApi, request) as api:
            taxa_ids = "+".join([str(x) for x in validated_categ_count.keys()])
            taxa: List[TaxonModel] = api.query_taxa_set(ids=taxa_ids)
        taxa_per_id = {taxon.id: taxon for taxon in taxa}

        # Get the number of validated objects of each category in each source project
        total_validated = sum(validated_categ_count.values())
        taxo_table = [[taxon_id, taxa_per_id[taxon_id].display_name, nbr_v,taxa_per_id[taxon_id].status]
                      for taxon_id, nbr_v in validated_categ_count.items()]
        taxo_table.sort(key=lambda r: r[2], reverse=True)
        # There are < in display names which make them unbreakable during resize
        for a_row in taxo_table:
            if "<" in a_row[1]:
                a_row[1] = a_row[1].replace("<", " < ")

        # Get previous settings which influence how to display the categories (pre-checked or not)
        d = DecodeEqualList(target_prj.classifsettings)
        categories_in_settings = d.get('seltaxo')
        if categories_in_settings:
            settings_taxo_set = {int(x) for x in categories_in_settings.split(',')}
        else:
            settings_taxo_set = {}
        g.TaxoList = [[r[0], r[1], r[2],
                       round(100 * r[2] / total_validated, 1),
                       'checked' if len(settings_taxo_set) == 0 or r[0] in settings_taxo_set else '',r[3]]
                      for r in taxo_table]  # Add object % and 'checked' or not

        src_prjs_str = ",&nbsp;".join(src_projs)
        return render_template('jobs/prediction_create_lsttaxo.html',
                               url=request.query_string.decode('utf-8'),
                               filters_info=filters_html,
                               src_prj_ids=src_prj_ids_sql,
                               src_prjs=src_prjs_str, prj=target_prj)

    @classmethod
    def GetFilterText(cls, filters_text) -> str:
        if filters_text:
            return "<p><span style='color:red;font-weight:bold;font-size:large;'" \
                   ">USING Active Project Filters</span><BR>Filters : " + filters_text + "</p>"
        else:
            return ""

    @classmethod
    def cook_no_object_message(cls, filters):
        msg = "No object to classify, perhaps all objects were already classified."
        if len(filters) > 0:
            msg += " Note that you have active filters, which reduces potential target objects."
        return msg

    @classmethod
    def GetAugmentedReverseObjectMap(cls, prj: ProjectModel):
        """ Return numerical free columns for a project + 2 hard-coded ones """
        ret = {k: v for k, v in prj.obj_free_cols.items() if v[0] == 'n'}
        for an_obj_var in cls.OBJECT_VARS:
            ret[an_obj_var] = an_obj_var
        return ret

    @classmethod
    def features_config_page(cls):
        # Third page of the wizard, proceed
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)

        src_prj_lst = gvp("src", gvg("src"))

        prev_settings = DecodeEqualList(target_prj.classifsettings)
        # Hidden FORM summarizing the previous steps choices
        hidden = {"src": src_prj_lst,
                  "learninglimit": int(gvp("learninglimit", "5000")),
                  # Reference for the 5000: Ricour Florian & al 2022
                  "features": prev_settings.get("critvar", ""),  # Chosen variables last time
                  "taxo": ",".join((x[4:] for x in request.form
                                    if x[0:4] == "taxo" and x[0:6] != "taxolb")),
                  "pre_mapping": ",".join((x[6:] + ":" + gvp(x) for x in request.form
                                           if x[0:6] == "taxolb")),
                  "testfraction": prev_settings.get("testfraction", "0"),
                  }

        # Determination des criteres/variables utilisées par l'algo de learning
        revobjmap = cls.GetAugmentedReverseObjectMap(target_prj)  # Dict NomVariable=>N° colonne ex Area:n42
        common_features = set(revobjmap.keys())

        # Loop over source projects, get their keys and determine a set of common keys (for dest + all srcs)
        # Note: given the hardcoded values in @see GetAugmentedReverseObjectMap, the common keys comprise
        # at least depth_min and depth_max
        revobjmapbaseByProj = {}
        src_prj_ids = [int(prj_id) for prj_id in src_prj_lst.split(",") if prj_id.isdigit()]

        src_projs = cls.api_read_projects(request, src_prj_ids, revobjmapbaseByProj, common_features)

        # critlist[feature] 0:feature , 1:% validated , 2:distinct
        critlist = {k: [k, -1, -1] for k in common_features}

        # Prepare names for the API call
        names_for_stats = ",".join(["fre.%s" % col for col in common_features if col not in cls.OBJECT_VARS])
        names_for_stats += ("," if names_for_stats else "") + ",".join(["obj.%s" % col for col in cls.OBJECT_VARS])
        # Stats on training set, i.e. projects+categories+limit
        with ApiClient(ProjectsApi, request) as api:
            stats: ProjectSetColumnStatsModel = \
                api.project_set_get_column_stats(ids=src_prj_lst,
                                                 names=names_for_stats,
                                                 limit=hidden["learninglimit"],
                                                 categories=hidden["taxo"])
        g.LsSize = stats.total
        for col, count, variance in zip(stats.columns, stats.counts, stats.variances):
            prfx, name = col.split(".", 1)
            critlist[name][1] = round(100 * (1 - count / stats.total))  # % Missing in source projects
            critlist[name][2] = ' ' if variance is None else ('Y' if variance != 0 else 'N')

        cnn_networks = set([target_prj.cnn_network_id] + [a_prj.cnn_network_id for a_prj in src_projs])
        g.SCN = target_prj.cnn_network_id and len(cnn_networks) == 1

        g.critlist = list(critlist.values())
        g.critlist.sort(key=lambda t: t[0])
        return render_template('jobs/prediction_create_settings.html',
                               header="", data=hidden,
                               filters_info=filters_html)

    @classmethod
    def testsplit_config_page(cls):
        # Fourth (final) page of the "train new model" wizard: name the model + held-out
        # test %, then the actual "start prediction task" submit.
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)

        prev_settings = DecodeEqualList(target_prj.classifsettings)
        # Hidden FORM carrying forward the previous steps' choices, as posted by the
        # features page's own form (@see prediction_create_settings.html)
        hidden = {"src": gvp("src"),
                  "taxo": gvp("Taxo"),
                  "learninglimit": gvp("learninglimit"),
                  "pre_mapping": gvp("PostTaxoMapping"),
                  "features": gvp("CritVar"),
                  "usescn": gvp("usescn"),
                  "testfraction": prev_settings.get("testfraction", "0"),
                  "modelname": gvp("modelname", ""),
                  }

        return render_template('jobs/prediction_create_testsplit.html',
                               header="", data=hidden,
                               filters_info=filters_html)

    #################################################################################################
    # "Re-train an existing model" sub-flow. Everything in the recipe (source projects,
    # categories, features, learning limit, held-out test %) is locked to the named model's
    # last training -- nothing here is re-asked or editable, only the current amount of
    # validated data is re-checked. @see plan doc for why: comparability across a model's
    # versions, and "retrain" is meant to be a one-click action once more data exists.

    @classmethod
    def workflow_start_page(cls):
        # Entry page when the project already has named model(s): choose "train a new
        # model" (today's wizard, unchanged) or "re-train" one of the listed ones.
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)
        with ApiClient(ProjectsApi, request) as api:
            models = api.get_trained_models(target_prj.projid)
        return render_template('jobs/prediction_create_start.html',
                               filters_info=filters_html,
                               projid=target_prj.projid,
                               models=models)

    @classmethod
    def _find_model(cls, target_prj: ProjectModel, model_name: str) -> Optional[dict]:
        with ApiClient(ProjectsApi, request) as api:
            models = api.get_trained_models(target_prj.projid)
        return next((m for m in models if m["name"] == model_name), None)

    @classmethod
    def _retrain_blocker(cls, target_prj: ProjectModel, model: dict) -> Optional[str]:
        """ None if a retrain can proceed, else an explanatory message. """
        config = model["config"]
        # 1. Has more been validated (in the locked source projects/categories) since the
        # model's last training? Reuses the same stats call categories_config_page() uses.
        src_ids_str = ",".join(str(x) for x in config["source_project_ids"])
        with ApiClient(ProjectsApi, request) as api:
            stats: List[ProjectTaxoStatsModel] = api.project_set_get_stats(ids=src_ids_str, taxa_ids="all")
        categories = set(config["categories"])
        current_validated = sum(
            a_stat.nb_validated for a_stat in stats
            if a_stat.used_taxa and a_stat.used_taxa[0] in categories and a_stat.nb_validated
        )
        last_size = model.get("learning_set_size") or 0
        if current_validated <= last_size:
            return ("No new validated objects since this model's last training on {0} "
                    "(still {1} validated, matching its source projects/categories). "
                    "Validate more objects before re-training.").format(
                model.get("training_start", "?"), current_validated)
        # 2. Are there objects to actually classify right now?
        filters: Dict[str, str] = {}
        cls._extract_filters_from_url(filters, target_prj)
        filters["statusfilter"] = "UP"
        with ApiClient(ObjectsApi, request) as api:
            res: ObjectSetQueryRsp = api.get_object_set(
                project_id=target_prj.projid, project_filters=filters, window_size=100)
        if len(res.object_ids) == 0:
            return cls.cook_no_object_message(filters)
        return None

    @classmethod
    def retrain_confirm_page(cls, model_name: str):
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)
        model = cls._find_model(target_prj, model_name)
        if model is None:
            flash("Model '%s' not found in this project" % model_name, "error")
            return cls.workflow_start_page()
        blocked_reason = cls._retrain_blocker(target_prj, model)
        with ApiClient(ProjectsApi, request) as api:
            history = api.get_training_history(target_prj.projid, model_name=model_name)
        return render_template('jobs/prediction_retrain_confirm.html',
                               filters_info=filters_html,
                               projid=target_prj.projid,
                               model_name=model_name, model=model,
                               blocked_reason=blocked_reason, history=history)

    @classmethod
    def retrain_start_task(cls):
        model_name = gvp("modelname", "")
        target_prj, filters_html = cls.get_target_project()
        if target_prj is None:
            return PrintInCharte(filters_html)
        model = cls._find_model(target_prj, model_name)
        if model is None:
            flash("Model '%s' not found in this project" % model_name, "error")
            return cls.workflow_start_page()
        # Re-check server-side rather than trust the confirm page's rendering.
        blocked_reason = cls._retrain_blocker(target_prj, model)
        if blocked_reason:
            flash(blocked_reason, "error")
            return cls.retrain_confirm_page(model_name)

        config = model["config"]
        filters: Dict[str, str] = {}
        cls._extract_filters_from_url(filters, target_prj)
        req = PredictionReq(project_id=target_prj.projid,
                            model_name=model_name,
                            source_project_ids=config["source_project_ids"],
                            learning_limit=config["learning_limit"],
                            categories=config["categories"],
                            features=config["features"],
                            use_scn=config["use_scn"],
                            pre_mapping=config["pre_mapping"],
                            test_fraction=config["test_fraction"])
        with ApiClient(ObjectsApi, request) as api:
            rsp: PredictionRsp = api.predict_object_set({'filters': filters,
                                                         'request': req})
        return redirect("/Job/Monitor/%d" % rsp.job_id)
