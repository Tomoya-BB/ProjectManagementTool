console.log('App initialized');
document.addEventListener('DOMContentLoaded', () => {
  const progress = document.getElementById('progress');
  const progressValue = document.getElementById('progressValue');
  if (progress && progressValue) {
    progress.addEventListener('input', () => {
      progressValue.value = progress.value;
    });
  }

  const modal = document.getElementById('editTaskModal');
  if (modal) {
    const modalProgress = document.getElementById('modalProgress');
    const modalProgressValue = document.getElementById('modalProgressValue');
    if (modalProgress && modalProgressValue) {
      modalProgress.addEventListener('input', () => {
        modalProgressValue.value = modalProgress.value;
      });
    }

    let taskId = null;
    document.querySelectorAll('.edit-task-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        taskId = btn.dataset.id;
        modal.querySelector('input[name="name"]').value = btn.dataset.name;
        modal.querySelector('input[name="start_date"]').value = btn.dataset.start;
        modal.querySelector('input[name="end_date"]').value = btn.dataset.end;
        modal.querySelector('select[name="resource_id"]').value = btn.dataset.resourceId || '';
        modal.querySelector('select[name="depends_on_id"]').value = btn.dataset.dependsOnId || '';
        modal.querySelector('input[name="is_milestone"]').checked = btn.dataset.isMilestone === 'True';
        modalProgress.value = btn.dataset.progress;
        modalProgressValue.value = btn.dataset.progress;
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
      });
    });

    const saveBtn = document.getElementById('saveTaskBtn');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        fetch('/task/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: taskId,
            name: modal.querySelector('input[name="name"]').value,
            start_date: modal.querySelector('input[name="start_date"]').value,
            end_date: modal.querySelector('input[name="end_date"]').value,
            progress: modalProgress.value,
            resource_id: modal.querySelector('select[name="resource_id"]').value || null,
            depends_on_id: modal.querySelector('select[name="depends_on_id"]').value || null,
            is_milestone: modal.querySelector('input[name="is_milestone"]').checked
          })
        }).then(res => {
          if (res.ok) {
            location.reload();
          } else {
            alert('Save failed');
          }
        });
      });
    }
  }
});
