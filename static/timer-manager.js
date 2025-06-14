// Timer Management for CAT Mock Tests
// This module provides coordinated timer management for section and total timers

class TimerManager {
    constructor(sectionTimerElement, totalTimerElement, testStructure) {
        this.sectionTimerElement = sectionTimerElement;
        this.totalTimerElement = totalTimerElement;
        this.testStructure = testStructure;
        
        // Timer state
        this.sectionTimeRemaining = 0;
        this.totalTimeRemaining = null;
        this.sectionIntervalId = null;
        this.totalIntervalId = null;
        
        // Callbacks
        this.onSectionTimeUp = null;
        this.onTotalTimeUp = null;
        this.onTimeUpdate = null;
        
        // Initialize total time only once
        this.initializeTotalTime();
    }
    
    initializeTotalTime() {
        if (this.totalTimeRemaining === null) {
            this.totalTimeRemaining = this.testStructure.reduce((sum, section) => 
                sum + section.timeLimitMinutes, 0) * 60;
        }
    }
    
    formatTime(seconds) {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
    }
    
    startSectionTimer(minutes) {
        this.stopSectionTimer();
        this.sectionTimeRemaining = minutes * 60;
        this.updateSectionDisplay();
        
        this.sectionIntervalId = setInterval(() => {
            if (this.sectionTimeRemaining > 0) {
                this.sectionTimeRemaining--;
                this.updateSectionDisplay();
                
                if (this.onTimeUpdate) {
                    this.onTimeUpdate('section', this.sectionTimeRemaining);
                }
            } else {
                this.stopSectionTimer();
                if (this.onSectionTimeUp) {
                    this.onSectionTimeUp();
                }
            }
        }, 1000);
    }
    
    stopSectionTimer() {
        if (this.sectionIntervalId) {
            clearInterval(this.sectionIntervalId);
            this.sectionIntervalId = null;
        }
    }
    
    startTotalTimer() {
        if (this.totalIntervalId || this.totalTimeRemaining <= 0) return;
        
        this.updateTotalDisplay();
        
        this.totalIntervalId = setInterval(() => {
            if (this.totalTimeRemaining > 0) {
                this.totalTimeRemaining--;
                this.updateTotalDisplay();
                
                if (this.onTimeUpdate) {
                    this.onTimeUpdate('total', this.totalTimeRemaining);
                }
            } else {
                this.stopAllTimers();
                if (this.onTotalTimeUp) {
                    this.onTotalTimeUp();
                }
            }
        }, 1000);
    }
    
    stopTotalTimer() {
        if (this.totalIntervalId) {
            clearInterval(this.totalIntervalId);
            this.totalIntervalId = null;
        }
    }
    
    stopAllTimers() {
        this.stopSectionTimer();
        this.stopTotalTimer();
    }
    
    updateSectionDisplay() {
        if (this.sectionTimerElement) {
            this.sectionTimerElement.textContent = this.formatTime(this.sectionTimeRemaining);
        }
    }
    
    updateTotalDisplay() {
        if (this.totalTimerElement) {
            this.totalTimerElement.textContent = this.formatTime(this.totalTimeRemaining);
        }
    }
    
    getRemainingTime() {
        return {
            section: this.sectionTimeRemaining,
            total: this.totalTimeRemaining
        };
    }
    
    getSectionTimeString() {
        return this.formatTime(this.sectionTimeRemaining);
    }
    
    getTotalTimeString() {
        return this.formatTime(this.totalTimeRemaining);
    }
    
    // Event handlers
    setSectionTimeUpHandler(callback) {
        this.onSectionTimeUp = callback;
    }
    
    setTotalTimeUpHandler(callback) {
        this.onTotalTimeUp = callback;
    }
    
    setTimeUpdateHandler(callback) {
        this.onTimeUpdate = callback;
    }
}

// Export for use in main script
window.TimerManager = TimerManager; 