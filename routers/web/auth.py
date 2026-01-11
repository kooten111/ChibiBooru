"""
Authentication routes for web interface.
"""

from quart import render_template, request, session, redirect, url_for, flash
import secrets
import config


def register_routes(blueprint):
    """Register authentication routes on the given blueprint."""
    
    @blueprint.route('/login', methods=['GET', 'POST'])
    async def login():
        if request.method == 'POST':
            form = await request.form
            if secrets.compare_digest(form.get('password', ''), config.APP_PASSWORD):
                session['logged_in'] = True
                session.permanent = True  # Session timeout configured in app.py (4 hours)
                return redirect(url_for('main.home'))
            else:
                await flash('Incorrect password.', 'error')
        return await render_template('login.html', app_name=config.APP_NAME)

    @blueprint.route('/logout')
    async def logout():
        session.pop('logged_in', None)
        await flash('You have been logged out.', 'info')
        return redirect(url_for('main.login'))
