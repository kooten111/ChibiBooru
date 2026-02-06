from typing import Any, Dict


def run_database_health_check(
    auto_fix: bool = True,
    include_thumbnails: bool = False,
    include_tag_deltas: bool = True,
) -> Dict[str, Any]:
    """Run database health checks and optionally fix issues."""
    from services import health_service as database_health

    results = database_health.run_all_health_checks(
        auto_fix=auto_fix,
        include_thumbnails=include_thumbnails,
        include_tag_deltas=include_tag_deltas,
    )
    return {
        "status": "success",
        "message": "Health check complete: {found} issues found, {fixed} fixed".format(
            found=results["total_issues_found"], fixed=results["total_issues_fixed"]
        ),
        "results": results,
    }
